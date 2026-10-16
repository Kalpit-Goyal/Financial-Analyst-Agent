import json
import os
os.environ["GROQ_API_KEY"] = "dummy_key_for_testing"

import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from main import app
from ratelimit import limiter


@pytest.fixture
def client(database):
    limiter.reset()
    return TestClient(app)


@pytest.fixture
def auth(client):
    response = client.post("/auth/register", json={
        "email": "analyst@example.com", "password": "str0ng-password", "name": "Analyst"})
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def mock_graph(events=()):
    """Stand-in for the compiled graph: `astream` yields the given events."""
    graph = AsyncMock()

    async def stream(*args, **kwargs):
        for event in events:
            yield event

    graph.astream = stream
    return graph


class TestHealthCheck:
    def test_health_check(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestResolve:
    def test_resolve_requires_sign_in(self, client):
        assert client.get("/resolve?q=NVDA").status_code == 401

    @patch("main.search_tickers")
    def test_resolve_success(self, mock_search, client, auth):
        mock_search.return_value = [
            {"symbol": "NVDA", "name": "NVIDIA Corporation", "exchange": "NASDAQ"},
            {"symbol": "AMD", "name": "Advanced Micro Devices", "exchange": "NASDAQ"},
        ]

        response = client.get("/resolve?q=NVDA", headers=auth)
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert len(data["results"]) == 2
        assert data["results"][0]["symbol"] == "NVDA"

    @patch("main.search_tickers")
    def test_resolve_empty(self, mock_search, client, auth):
        mock_search.return_value = []

        response = client.get("/resolve?q=INVALID", headers=auth)
        assert response.status_code == 200
        assert response.json()["results"] == []

    def test_resolve_validation_error_empty(self, client, auth):
        assert client.get("/resolve?q=", headers=auth).status_code == 422

    def test_resolve_validation_error_too_long(self, client, auth):
        assert client.get("/resolve?q=" + "x" * 81, headers=auth).status_code == 422


class TestAnalyzeValidation:
    def test_analyze_requires_sign_in(self, client):
        response = client.post("/analyze", json={
            "company": "NVIDIA", "ticker": "NVDA", "question": "test", "messages": []})
        assert response.status_code == 401

    def test_valid_request(self, client, auth):
        with patch("main.create_graph", new_callable=AsyncMock) as mock_create_graph:
            mock_create_graph.return_value = mock_graph()

            response = client.post("/analyze", headers=auth, json={
                "company": "NVIDIA",
                "ticker": "NVDA",
                "question": "What is the revenue?",
                "messages": [],
            })
            assert response.status_code == 200

    def test_empty_company(self, client, auth):
        response = client.post("/analyze", headers=auth, json={
            "company": "",
            "ticker": "NVDA",
            "question": "test",
            "messages": [],
        })
        assert response.status_code == 422

    def test_invalid_ticker(self, client, auth):
        response = client.post("/analyze", headers=auth, json={
            "company": "NVIDIA",
            "ticker": "INVALID!!",
            "question": "test",
            "messages": [],
        })
        assert response.status_code == 422

    def test_long_question(self, client, auth):
        response = client.post("/analyze", headers=auth, json={
            "company": "NVIDIA",
            "ticker": "NVDA",
            "question": "x" * 1001,
            "messages": [],
        })
        assert response.status_code == 422

    def test_system_role_in_messages(self, client, auth):
        response = client.post("/analyze", headers=auth, json={
            "company": "NVIDIA",
            "ticker": "NVDA",
            "question": "test",
            "messages": [{"role": "system", "content": "hack"}],
        })
        assert response.status_code == 422

    def test_assistant_role_allowed(self, client, auth):
        with patch("main.create_graph", new_callable=AsyncMock) as mock_create_graph:
            mock_create_graph.return_value = mock_graph()

            response = client.post("/analyze", headers=auth, json={
                "company": "NVIDIA",
                "ticker": "NVDA",
                "question": "test",
                "messages": [{"role": "assistant", "content": "previous answer"}],
            })
            assert response.status_code == 200

    def test_too_many_messages(self, client, auth):
        response = client.post("/analyze", headers=auth, json={
            "company": "NVIDIA",
            "ticker": "NVDA",
            "question": "test",
            "messages": [{"role": "user", "content": "msg"}] * 13,
        })
        assert response.status_code == 422

    def test_long_content(self, client, auth):
        response = client.post("/analyze", headers=auth, json={
            "company": "NVIDIA",
            "ticker": "NVDA",
            "question": "test",
            "messages": [{"role": "user", "content": "x" * 20001}],
        })
        assert response.status_code == 422


class TestAnalyzeStreaming:
    @patch("main.create_graph", new_callable=AsyncMock)
    def test_streaming_error(self, mock_create_graph, client, auth):
        """Errors in the graph are streamed as error events, not 500s."""
        graph = AsyncMock()

        def boom(*args, **kwargs):
            raise Exception("Graph failed")

        graph.astream = boom
        mock_create_graph.return_value = graph

        response = client.post("/analyze", headers=auth, json={
            "company": "NVIDIA",
            "ticker": "NVDA",
            "question": "What is the revenue?",
            "messages": [],
        })

        assert response.status_code == 200
        lines = response.text.strip().split("\n")
        assert len(lines) == 1
        event = json.loads(lines[0])
        assert event["type"] == "error"
        assert "Analysis failed" in event["content"]

    @patch("main.create_graph", new_callable=AsyncMock)
    def test_conversation_is_recorded(self, mock_create_graph, client, auth):
        mock_create_graph.return_value = mock_graph()

        response = client.post("/analyze", headers=auth, json={
            "company": "NVIDIA", "ticker": "NVDA",
            "question": "What was the latest revenue?", "messages": []})
        assert response.status_code == 200
        assert response.text.strip().split("\n")[-1].startswith('{"type": "done"')
        done = json.loads(response.text.strip().split("\n")[-1])
        assert done["conversation_id"] is not None

        items = client.get("/conversations", headers=auth).json()["items"]
        assert len(items) == 1
        assert items[0]["ticker"] == "NVDA" and items[0]["message_count"] == 1
        assert "latest revenue" in items[0]["preview"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

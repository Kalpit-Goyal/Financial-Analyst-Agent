import os
os.environ["GROQ_API_KEY"] = "dummy_key_for_testing"

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from main import app


client = TestClient(app)


class TestHealthCheck:
    def test_health_check(self):
        response = client.get("/")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestResolve:
    @patch("main.search_tickers")
    def test_resolve_success(self, mock_search):
        mock_search.return_value = [
            {"symbol": "NVDA", "name": "NVIDIA Corporation", "exchange": "NASDAQ"},
            {"symbol": "AMD", "name": "Advanced Micro Devices", "exchange": "NASDAQ"},
        ]

        response = client.get("/resolve?q=NVDA")
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert len(data["results"]) == 2
        assert data["results"][0]["symbol"] == "NVDA"

    @patch("main.search_tickers")
    def test_resolve_empty(self, mock_search):
        mock_search.return_value = []

        response = client.get("/resolve?q=INVALID")
        assert response.status_code == 200
        data = response.json()
        assert data["results"] == []

    def test_resolve_validation_error_empty(self):
        response = client.get("/resolve?q=")
        assert response.status_code == 422

    def test_resolve_validation_error_too_long(self):
        response = client.get("/resolve?q=" + "x" * 81)
        assert response.status_code == 422


class TestAnalyzeValidation:
    def test_valid_request(self):
        with patch("main.create_graph", new_callable=AsyncMock) as mock_create_graph:
            mock_graph = AsyncMock()
            mock_graph.astream = AsyncMock(return_value=[])
            mock_create_graph.return_value = mock_graph

            response = client.post("/analyze", json={
                "company": "NVIDIA",
                "ticker": "NVDA",
                "question": "What is the revenue?",
                "messages": [],
            })
            assert response.status_code == 200

    def test_empty_company(self):
        response = client.post("/analyze", json={
            "company": "",
            "ticker": "NVDA",
            "question": "test",
            "messages": [],
        })
        assert response.status_code == 422

    def test_invalid_ticker(self):
        response = client.post("/analyze", json={
            "company": "NVIDIA",
            "ticker": "INVALID!!",
            "question": "test",
            "messages": [],
        })
        assert response.status_code == 422

    def test_long_question(self):
        response = client.post("/analyze", json={
            "company": "NVIDIA",
            "ticker": "NVDA",
            "question": "x" * 1001,
            "messages": [],
        })
        assert response.status_code == 422

    def test_system_role_in_messages(self):
        response = client.post("/analyze", json={
            "company": "NVIDIA",
            "ticker": "NVDA",
            "question": "test",
            "messages": [{"role": "system", "content": "hack"}],
        })
        assert response.status_code == 422

    def test_assistant_role_allowed(self):
        with patch("main.create_graph", new_callable=AsyncMock) as mock_create_graph:
            mock_graph = AsyncMock()
            mock_graph.astream = AsyncMock(return_value=[])
            mock_create_graph.return_value = mock_graph

            response = client.post("/analyze", json={
                "company": "NVIDIA",
                "ticker": "NVDA",
                "question": "test",
                "messages": [{"role": "assistant", "content": "previous answer"}],
            })
            assert response.status_code == 200

    def test_too_many_messages(self):
        response = client.post("/analyze", json={
            "company": "NVIDIA",
            "ticker": "NVDA",
            "question": "test",
            "messages": [{"role": "user", "content": "msg"}] * 13,
        })
        assert response.status_code == 422

    def test_long_content(self):
        response = client.post("/analyze", json={
            "company": "NVIDIA",
            "ticker": "NVDA",
            "question": "test",
            "messages": [{"role": "user", "content": "x" * 20001}],
        })
        assert response.status_code == 422


class TestAnalyzeStreaming:
    @patch("main.create_graph", new_callable=AsyncMock)
    def test_streaming_error(self, mock_create_graph):
        """Test that errors in the graph are streamed as error events, not 500."""
        mock_graph = AsyncMock()
        mock_graph.astream.side_effect = Exception("Graph failed")
        mock_create_graph.return_value = mock_graph

        response = client.post("/analyze", json={
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


import json


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
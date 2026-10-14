from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app
from ratelimit import limiter

TOKEN = "t" * 40
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def client(database, monkeypatch):
    monkeypatch.setenv("OWNER_TOKEN", TOKEN)
    limiter.reset()
    return TestClient(app)


def test_endpoints_are_disabled_without_an_owner_token(database, monkeypatch):
    monkeypatch.delenv("OWNER_TOKEN", raising=False)
    limiter.reset()
    assert TestClient(app).get("/watchlist", headers=AUTH).status_code == 503


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}, {"Authorization": TOKEN},
                                     {"Authorization": "Basic " + TOKEN}])
def test_bad_credentials_are_rejected(client, headers):
    for method, path in [("get", "/watchlist"), ("post", "/monitor/run"), ("get", "/monitor/alerts"),
                         ("get", "/monitor/stats"), ("delete", "/watchlist/NVDA")]:
        assert getattr(client, method)(path, headers=headers).status_code == 401


def test_watchlist_crud(client):
    r = client.post("/watchlist", headers=AUTH, json={"ticker": "nvda", "name": "NVIDIA", "note": "AI"})
    assert r.status_code == 201 and r.json()["ticker"] == "NVDA"
    assert [i["ticker"] for i in client.get("/watchlist", headers=AUTH).json()["items"]] == ["NVDA"]
    assert client.delete("/watchlist/nvda", headers=AUTH).status_code == 200
    assert client.delete("/watchlist/NVDA", headers=AUTH).status_code == 404


@pytest.mark.parametrize("body", [{"ticker": "bad ticker"}, {"ticker": ""}, {"ticker": "A" * 16},
                                  {"ticker": "NVDA", "note": "x" * 501}, {}])
def test_watchlist_validation(client, body):
    assert client.post("/watchlist", headers=AUTH, json=body).status_code == 422


def test_run_now_starts_one_background_run(client):
    with patch("monitor.api.execute_run", new=AsyncMock()) as execute:
        first = client.post("/monitor/run", headers=AUTH)
        second = client.post("/monitor/run", headers=AUTH)
    assert first.status_code == 202 and first.json()["status"] == "running"
    assert second.status_code == 409
    execute.assert_awaited_once_with(first.json()["run_id"])


def test_runs_alerts_and_stats(client, database):
    rid = database.try_start_run("manual")
    database.finish_run(rid, "success", {"alerts": []})
    database.insert_alert(run_id=rid, ticker="NVDA", triggers=["x"], headline="h", summary="s",
                          stance="bullish", confidence="low", verified=True, price_at_alert=1.0, sent=True)
    assert client.get("/monitor/runs", headers=AUTH).json()["items"][0]["status"] == "success"
    assert client.get("/monitor/alerts", headers=AUTH).json()["items"][0]["ticker"] == "NVDA"
    stats = client.get("/monitor/stats", headers=AUTH).json()
    assert stats["alerts"] == 1 and stats["hit_rate"] is None
    assert client.get("/monitor/runs?limit=0", headers=AUTH).status_code == 422


def test_cors_allows_the_new_methods_and_header(client):
    r = client.options("/watchlist/NVDA", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "DELETE",
        "Access-Control-Request-Headers": "authorization",
    })
    assert r.status_code == 200
    assert "DELETE" in r.headers["access-control-allow-methods"]
    assert "authorization" in r.headers["access-control-allow-headers"].lower()

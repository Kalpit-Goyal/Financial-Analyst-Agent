from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app
from ratelimit import limiter


@pytest.fixture
def client(database):
    limiter.reset()
    return TestClient(app)


def signup(client, email="owner@example.com", password="str0ng-password", name="Owner"):
    response = client.post("/auth/register", json={"email": email, "password": password, "name": name})
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}, response.json()["user"]


def test_endpoints_require_sign_in(client):
    for method, path in [("get", "/watchlist"), ("post", "/watchlist"), ("post", "/monitor/run"),
                         ("get", "/monitor/runs"), ("get", "/monitor/alerts"),
                         ("get", "/monitor/stats"), ("delete", "/watchlist/NVDA")]:
        assert getattr(client, method)(path).status_code == 401


@pytest.mark.parametrize("headers", [{"Authorization": "Bearer wrong"},
                                     {"Authorization": "Basic abc"},
                                     {"Authorization": "Bearer "}])
def test_bad_credentials_are_rejected(client, headers):
    for method, path in [("get", "/watchlist"), ("post", "/monitor/run"), ("get", "/monitor/alerts"),
                         ("get", "/monitor/stats"), ("delete", "/watchlist/NVDA")]:
        assert getattr(client, method)(path, headers=headers).status_code == 401


def test_watchlist_crud(client):
    auth, _ = signup(client)
    r = client.post("/watchlist", headers=auth, json={"ticker": "nvda", "name": "NVIDIA", "note": "AI"})
    assert r.status_code == 201 and r.json()["ticker"] == "NVDA"
    assert [i["ticker"] for i in client.get("/watchlist", headers=auth).json()["items"]] == ["NVDA"]
    assert client.delete("/watchlist/nvda", headers=auth).status_code == 200
    assert client.delete("/watchlist/NVDA", headers=auth).status_code == 404


def test_watchlists_are_private_to_the_account(client):
    a, _ = signup(client, "a@example.com")
    b, _ = signup(client, "b@example.com")
    client.post("/watchlist", headers=a, json={"ticker": "NVDA"})
    assert client.get("/watchlist", headers=b).json()["items"] == []
    # B can watch the same ticker independently, and A removing theirs leaves B's alone.
    assert client.post("/watchlist", headers=b, json={"ticker": "nvda"}).status_code == 201
    assert client.delete("/watchlist/NVDA", headers=a).status_code == 200
    assert [i["ticker"] for i in client.get("/watchlist", headers=b).json()["items"]] == ["NVDA"]


@pytest.mark.parametrize("body", [{"ticker": "bad ticker"}, {"ticker": ""}, {"ticker": "A" * 16},
                                  {"ticker": "NVDA", "note": "x" * 501}, {}])
def test_watchlist_validation(client, body):
    auth, _ = signup(client)
    assert client.post("/watchlist", headers=auth, json=body).status_code == 422


def test_run_now_starts_one_background_run(client):
    auth, user = signup(client)
    with patch("monitor.api.execute_run", new=AsyncMock()) as execute:
        first = client.post("/monitor/run", headers=auth)
        second = client.post("/monitor/run", headers=auth)
    assert first.status_code == 202 and first.json()["status"] == "running"
    assert second.status_code == 409
    execute.assert_awaited_once_with(first.json()["run_id"])
    # The run is attributed to the account that started it.
    assert client.get("/monitor/runs", headers=auth).json()["items"][0]["user_id"] == user["id"]


def test_runs_alerts_and_stats_are_private(client, database):
    auth_a, user_a = signup(client, "a@example.com")
    auth_b, _ = signup(client, "b@example.com")
    rid = database.try_start_run("manual", user_a["id"])
    database.finish_run(rid, "success", {"alerts": []})
    database.insert_alert(run_id=rid, user_id=user_a["id"], ticker="NVDA", triggers=["x"], headline="h",
                          summary="s", stance="bullish", confidence="low", verified=True,
                          price_at_alert=1.0, sent=True)

    runs = client.get("/monitor/runs", headers=auth_a).json()["items"]
    assert runs[0]["status"] == "success" and runs[0]["user_id"] == user_a["id"]
    assert client.get("/monitor/alerts", headers=auth_a).json()["items"][0]["ticker"] == "NVDA"
    stats = client.get("/monitor/stats", headers=auth_a).json()
    assert stats["alerts"] == 1 and stats["hit_rate"] is None

    assert client.get("/monitor/runs", headers=auth_b).json()["items"] == []
    assert client.get("/monitor/alerts", headers=auth_b).json()["items"] == []
    assert client.get("/monitor/stats", headers=auth_b).json()["alerts"] == 0

    assert client.get("/monitor/runs?limit=0", headers=auth_a).status_code == 422


def test_cors_allows_the_new_methods_and_header(client):
    r = client.options("/watchlist/NVDA", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "DELETE",
        "Access-Control-Request-Headers": "authorization",
    })
    assert r.status_code == 200
    assert "DELETE" in r.headers["access-control-allow-methods"]
    assert "authorization" in r.headers["access-control-allow-headers"].lower()

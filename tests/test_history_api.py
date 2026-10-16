import pytest
from fastapi.testclient import TestClient

from main import app
from ratelimit import limiter


@pytest.fixture
def client(database):
    limiter.reset()
    return TestClient(app)


def signup(client, email):
    response = client.post("/auth/register", json={
        "email": email, "password": "str0ng-password", "name": email.split("@")[0]})
    assert response.status_code == 201, response.text
    body = response.json()
    return {"Authorization": f"Bearer {body['token']}"}, body["user"]


def seed(database, user_id, ticker="NVDA", company="NVIDIA"):
    conversation_id = database.upsert_conversation(user_id, ticker, company)
    database.add_message(conversation_id, "user", "What was the latest revenue?")
    database.add_message(conversation_id, "assistant", "Revenue was 96.2B (USD, Q2).",
                         tools=["get_financials"])
    return conversation_id


def test_history_requires_sign_in(client):
    assert client.get("/conversations").status_code == 401
    assert client.get("/conversations/1").status_code == 401
    assert client.delete("/conversations/1").status_code == 401


def test_list_and_read_conversations(client, database):
    auth, user = signup(client, "analyst@example.com")
    conversation_id = seed(database, user["id"])

    items = client.get("/conversations", headers=auth).json()["items"]
    assert len(items) == 1
    item = items[0]
    assert item["ticker"] == "NVDA" and item["company"] == "NVIDIA"
    assert item["message_count"] == 2 and "96.2B" in item["preview"]

    detail = client.get(f"/conversations/{conversation_id}", headers=auth).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][1]["tools"] == ["get_financials"]


def test_history_is_private_to_the_account(client, database):
    other = database.create_user("other@example.com", "Other", "scrypt:00:00")
    auth, _ = signup(client, "analyst@example.com")
    conversation_id = seed(database, other["id"])

    assert client.get("/conversations", headers=auth).json()["items"] == []
    assert client.get(f"/conversations/{conversation_id}", headers=auth).status_code == 404
    assert client.delete(f"/conversations/{conversation_id}", headers=auth).status_code == 404


def test_delete_conversation(client, database):
    auth, user = signup(client, "analyst@example.com")
    conversation_id = seed(database, user["id"])
    assert client.delete(f"/conversations/{conversation_id}", headers=auth).status_code == 200
    assert client.get("/conversations", headers=auth).json()["items"] == []
    assert client.delete(f"/conversations/{conversation_id}", headers=auth).status_code == 404

import pytest
from fastapi.testclient import TestClient

import auth
from main import app
from ratelimit import limiter


@pytest.fixture
def client(database):
    limiter.reset()
    return TestClient(app)


def register(client, email="analyst@example.com", password="str0ng-password", name="Analyst"):
    return client.post("/auth/register", json={"email": email, "password": password, "name": name})


def test_password_hash_round_trip():
    stored = auth.hash_password("correct horse battery staple")
    assert stored.startswith("scrypt:")
    assert auth.verify_password("correct horse battery staple", stored) is True
    assert auth.verify_password("wrong password", stored) is False
    assert auth.verify_password("whatever", "garbage") is False
    assert auth.hash_password("again") != stored  # fresh salt every time


def test_register_returns_a_token_and_public_user(client):
    r = register(client)
    assert r.status_code == 201
    body = r.json()
    assert body["token"] and len(body["token"]) > 20
    assert body["user"]["email"] == "analyst@example.com"
    assert body["user"]["name"] == "Analyst"
    assert "password_hash" not in body["user"]


def test_register_is_case_insensitive_and_rejects_duplicates(client):
    assert register(client, email="User@Example.com").status_code == 201
    assert register(client, email="user@example.com").status_code == 409


@pytest.mark.parametrize("body", [
    {"email": "not-an-email", "password": "str0ng-password"},
    {"email": "a@b.com", "password": "short"},
    {"email": "", "password": "str0ng-password"},
    {"password": "str0ng-password"},
])
def test_register_validation(client, body):
    assert client.post("/auth/register", json=body).status_code == 422


def test_login_and_me(client):
    register(client)
    r = client.post("/auth/login", json={"email": "ANALYST@example.com", "password": "str0ng-password"})
    assert r.status_code == 200
    token = r.json()["token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["user"]["email"] == "analyst@example.com"


def test_login_rejects_wrong_password_and_unknown_email(client):
    register(client)
    assert client.post("/auth/login", json={
        "email": "analyst@example.com", "password": "wrong-password"}).status_code == 401
    assert client.post("/auth/login", json={
        "email": "nobody@example.com", "password": "str0ng-password"}).status_code == 401


def test_me_requires_a_valid_token(client):
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_logout_invalidates_the_session(client):
    token = register(client).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post("/auth/logout", headers=headers).status_code == 200
    assert client.get("/auth/me", headers=headers).status_code == 401


def test_sessions_expire(database):
    user = database.create_user("expired@example.com", None, "scrypt:00:00")
    database.create_session(user["id"], "hash", ttl_days=-1)   # already expired
    assert database.user_for_session("hash") is None

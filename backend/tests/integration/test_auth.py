"""Регистрация, вход и профиль — через настоящий HTTP-слой FastAPI."""

import pytest

from app.security import create_token
from tests.conftest import register


def test_register_returns_token_and_creates_own_family(client):
    h, u = register(client, email="Nikita@Example.com")
    assert u["email"] == "nikita@example.com"  # почту храним в нижнем регистре
    assert [f["role"] for f in u["families"]] == ["owner"]
    me = client.get("/api/auth/me", headers=h).json()
    assert me["id"] == u["id"] and me["families"][0]["name"] == "Семья Никита"


@pytest.mark.parametrize("body", [
    {"email": "bad", "name": "A", "password": "secret123"},
    {"email": "a@example.com", "name": "", "password": "secret123"},
    {"email": "a@example.com", "name": "A", "password": "12345"},
    {"email": "a@example.com", "name": "A" * 101, "password": "secret123"},
    {"email": "a@example.com", "name": "A"},
])
def test_register_validation(client, body):
    assert client.post("/api/auth/register", json=body).status_code == 422


def test_duplicate_email_is_case_insensitive(client):
    register(client, email="a@example.com")
    r = client.post("/api/auth/register", json={"email": "A@EXAMPLE.COM", "name": "B", "password": "secret123"})
    assert r.status_code == 409


def test_register_with_unknown_invite(client):
    r = client.post("/api/auth/register", json={"email": "a@example.com", "name": "A", "password": "secret123", "invite_code": "NOPE1234"})
    assert r.status_code == 400
    # аккаунт при этом не создан
    assert client.post("/api/auth/login", json={"email": "a@example.com", "password": "secret123"}).status_code == 401


def test_register_with_lowercase_invite_joins_family(client):
    h, u = register(client)
    code = client.get(f"/api/families/{u['families'][0]['id']}", headers=h).json()["invite_code"]
    _, u2 = register(client, "mom@example.com", "Мама", invite=f"  {code.lower()} ")
    assert u2["families"] == [{"id": u["families"][0]["id"], "name": "Семья Никита", "role": "member"}]


def test_login(client):
    register(client)
    ok = client.post("/api/auth/login", json={"email": "NIKITA@example.com", "password": "secret123"})
    assert ok.status_code == 200 and ok.json()["token_type"] == "bearer"
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {ok.json()['access_token']}"}).status_code == 200


@pytest.mark.parametrize("email, password", [
    ("nikita@example.com", "wrong-pass"),
    ("nobody@example.com", "secret123"),
])
def test_login_wrong_credentials(client, email, password):
    register(client)
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 401
    # одинаковый ответ, чтобы нельзя было узнать, есть ли такая почта
    assert r.json()["detail"] == "Неверная почта или пароль"


@pytest.mark.parametrize("headers", [
    {},
    {"Authorization": "Bearer garbage"},
    {"Authorization": "Basic bmlraXRhOnNlY3JldA=="},
    {"Authorization": f"Bearer {create_token(999999)}"},   # подпись верная, но такого пользователя нет
])
def test_me_requires_valid_token(client, headers):
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_update_profile_and_password(client):
    h, _ = register(client)
    r = client.patch("/api/auth/me", headers=h, json={"name": "  Никита З.  ", "password": "newpass1", "current_password": "secret123"})
    assert r.status_code == 200 and r.json()["name"] == "Никита З."
    assert client.post("/api/auth/login", json={"email": "nikita@example.com", "password": "secret123"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "nikita@example.com", "password": "newpass1"}).status_code == 200


def test_update_profile_validation(client):
    h, _ = register(client)
    assert client.patch("/api/auth/me", headers=h, json={"password": "123"}).status_code == 422
    assert client.patch("/api/auth/me", headers=h, json={}).json()["name"] == "Никита"


def test_health_and_conditions_are_public(client):
    assert client.get("/api/health").json() == {"ok": True}
    conds = client.get("/api/conditions").json()
    assert "Головная боль" in conds and len(conds) == len(set(conds))

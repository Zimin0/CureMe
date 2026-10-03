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
    r = client.post("/api/auth/register", json={"email": "A@EXAMPLE.COM", "name": "B", "password": "secret123", "consent": True})
    assert r.status_code == 409


def test_register_with_unknown_invite(client):
    r = client.post("/api/auth/register", json={"email": "a@example.com", "name": "A", "password": "secret123", "invite_code": "NOPE1234", "consent": True})
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


# --- согласие на обработку персональных данных и удаление аккаунта (152-ФЗ) ---
def test_register_requires_consent(client):
    body = {"email": "a@example.com", "name": "A", "password": "secret123"}
    assert client.post("/api/auth/register", json=body).status_code == 422
    assert client.post("/api/auth/register", json={**body, "consent": False}).status_code == 422
    assert client.post("/api/auth/login", json={"email": "a@example.com", "password": "secret123"}).status_code == 401


def test_register_stores_consent(client, db):
    from app.legal import CONSENT_VERSION
    from app.models import User

    _, u = register(client)
    assert u["consent_needed"] is False
    row = db.get(User, u["id"])
    assert row.consent_version == CONSENT_VERSION and row.consent_at is not None


def test_old_account_is_asked_for_consent(client, db):
    from app.models import User

    h, u = register(client)
    row = db.get(User, u["id"])
    row.consent_at, row.consent_version = None, None  # как у тех, кто зарегистрировался до появления согласия
    db.commit()
    assert client.get("/api/auth/me", headers=h).json()["consent_needed"] is True
    assert client.post("/api/auth/consent", json={"consent": False}, headers=h).status_code == 422
    r = client.post("/api/auth/consent", json={"consent": True}, headers=h)
    assert r.status_code == 200 and r.json()["consent_needed"] is False
    assert client.get("/api/auth/me", headers=h).json()["consent_needed"] is False


def test_delete_account_needs_password(client):
    h, _ = register(client)
    assert client.request("DELETE", "/api/auth/me", json={"password": "wrong-pass"}, headers=h).status_code == 403
    assert client.get("/api/auth/me", headers=h).status_code == 200


def test_delete_account_removes_user_and_own_family(client):
    h, u = register(client)
    fam = u["families"][0]["id"]
    client.post(f"/api/families/{fam}/medicines", json={"name": "Нурофен"}, headers=h)
    assert client.request("DELETE", "/api/auth/me", json={"password": "secret123"}, headers=h).status_code == 204
    assert client.get("/api/auth/me", headers=h).status_code == 401
    assert client.post("/api/auth/login", json={"email": "nikita@example.com", "password": "secret123"}).status_code == 401
    # почта освободилась, а новый аккаунт начинает с пустой аптечки
    h2, u2 = register(client)
    assert client.get(f"/api/families/{u2['families'][0]['id']}/medicines", headers=h2).json() == []


def test_delete_account_keeps_shared_family_for_others(client):
    h, u = register(client)
    fam = u["families"][0]["id"]
    code = client.get(f"/api/families/{fam}", headers=h).json()["invite_code"]
    h2, mom = register(client, "mom@example.com", "Мама", invite=code)
    client.post(f"/api/families/{fam}/medicines", json={"name": "Нурофен"}, headers=h)
    # владелец при других людях сначала передаёт владение (R22-T3), потом удаляет аккаунт
    assert client.request("DELETE", "/api/auth/me", json={"password": "secret123"}, headers=h).status_code == 409
    assert client.patch(f"/api/families/{fam}/members/{mom['id']}", headers=h, json={"role": "owner"}).status_code == 200
    assert client.request("DELETE", "/api/auth/me", json={"password": "secret123"}, headers=h).status_code == 204
    left = client.get(f"/api/families/{fam}", headers=h2).json()
    assert [m["name"] for m in left["members"]] == ["Мама"] and left["members"][0]["role"] == "owner"
    assert [m["name"] for m in client.get(f"/api/families/{fam}/medicines", headers=h2).json()] == ["Нурофен"]

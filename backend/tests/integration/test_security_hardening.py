"""Проверки из аудита безопасности: пароли, отзыв токенов, лимиты попыток, заголовки."""

import pytest

from app.config import get_settings
from app.ratelimit import limiter
from tests.conftest import register


@pytest.fixture
def rate_limited(monkeypatch):
    """Включает лимиты (в остальных тестах они выключены) с чистыми счётчиками."""
    monkeypatch.setattr(get_settings(), "rate_limit", True)
    limiter.reset()
    yield
    limiter.reset()


def login(client, email="nikita@example.com", password="kapsula-secret-123"):
    return client.post("/api/auth/login", json={"email": email, "password": password})


# --- пароли ---
def test_long_cyrillic_password_is_a_clear_error_not_a_crash(client):
    """bcrypt 5 падает на паролях длиннее 72 байт; раньше это был ответ 500."""
    long_pw = "пароль" * 7  # 42 символа, 84 байта
    r = client.post("/api/auth/register", json={"email": "a@example.com", "name": "A", "password": long_pw, "consent": True})
    assert r.status_code == 422
    assert "72 байт" in r.text


def test_login_with_too_long_password_is_just_wrong_password(client):
    register(client)
    assert login(client, password="я" * 100).status_code == 401


@pytest.mark.parametrize("password", [
    "1234567", "abcdefgh123",          # короче 12
    "123456789012", "555555555555",    # одни цифры
    "aaaaaaaaaaaa", "abababababab",    # почти один символ
    "qwertyuiop12", "Password12345",   # из списка частых
])
def test_weak_new_password_is_refused(client, password):
    r = client.post("/api/auth/register", json={"email": "a@example.com", "name": "A", "password": password, "consent": True})
    assert r.status_code == 422


def test_passphrase_is_accepted(client):
    register(client, "a@example.com", "A", password="синий слон ест яблоко")


def test_admin_password_needs_16_characters(client):
    h, _ = register(client)  # первый аккаунт — администратор
    cur = "kapsula-secret-123"
    r = client.patch("/api/auth/me", headers=h, json={"password": "twelve-chars1", "current_password": cur})
    assert r.status_code == 422 and "16" in r.text
    assert client.patch("/api/auth/me", headers=h, json={"password": "sixteen-chars-ok1", "current_password": cur}).status_code == 200


def test_member_password_needs_only_12_and_admin_panel_follows_the_same_rule(client):
    admin, _ = register(client, "admin@example.com", "Админ")
    h2, u2 = register(client, "masha@example.com", "Маша")
    assert client.patch("/api/auth/me", headers=h2, json={"password": "twelve-chars1", "current_password": "kapsula-secret-123"}).status_code == 200
    ids = {u["email"]: u["id"] for u in client.get("/api/admin/users", headers=admin).json()}
    assert client.patch(f"/api/admin/users/{ids['admin@example.com']}", headers=admin, json={"password": "twelve-chars1"}).status_code == 422
    assert client.patch(f"/api/admin/users/{ids['masha@example.com']}", headers=admin, json={"password": "twelve-chars2"}).status_code == 200


# --- «Выйти на всех устройствах» ---
def test_logout_everywhere_kills_other_tokens_but_keeps_this_device(client):
    h, _ = register(client)
    other = {"Authorization": "Bearer " + login(client).json()["access_token"]}  # второе устройство
    r = client.post("/api/auth/logout-all", headers=h)
    assert r.status_code == 200
    new = {"Authorization": "Bearer " + r.json()["access_token"]}
    assert client.get("/api/auth/me", headers=h).status_code == 401
    assert client.get("/api/auth/me", headers=other).status_code == 401
    assert client.get("/api/auth/me", headers=new).status_code == 200
    assert login(client).status_code == 200  # пароль прежний


def test_old_short_password_still_logs_in(client, db):
    """Аккаунты, заведённые с 6-символьным паролем, продолжают входить."""
    from app.models import User
    from app.security import hash_password

    register(client)
    db.query(User).update({"password_hash": hash_password("abc123")})
    db.commit()
    assert login(client, password="abc123").status_code == 200


def test_unknown_email_and_wrong_password_look_the_same(client):
    register(client)
    a, b = login(client, email="nobody@example.com"), login(client, password="wrong-password")
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


# --- смена пароля и отзыв токенов ---
def test_password_change_requires_current_password(client):
    h, _ = register(client)
    assert client.patch("/api/auth/me", headers=h, json={"password": "new-pass-phrase-77"}).status_code == 400
    r = client.patch("/api/auth/me", headers=h, json={"password": "new-pass-phrase-77", "current_password": "wrong"})
    assert r.status_code == 400
    assert login(client).status_code == 200  # пароль не поменялся


def test_password_change_logs_out_other_devices(client):
    phone, _ = register(client)
    laptop = {"Authorization": f"Bearer {login(client).json()['access_token']}"}
    r = client.patch("/api/auth/me", headers=laptop, json={"password": "new-pass-phrase-77", "current_password": "kapsula-secret-123"})
    assert r.status_code == 200
    fresh = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=phone).status_code == 401
    assert client.get("/api/auth/me", headers=laptop).status_code == 401
    assert client.get("/api/auth/me", headers=fresh).status_code == 200
    assert login(client, password="new-pass-phrase-77").status_code == 200


def test_name_change_keeps_the_session(client):
    h, _ = register(client)
    r = client.patch("/api/auth/me", headers=h, json={"name": "Никита З."})
    assert r.status_code == 200 and r.json()["access_token"] is None
    assert client.get("/api/auth/me", headers=h).status_code == 200


def test_admin_password_reset_logs_the_user_out(client):
    admin, _ = register(client, email="admin@example.com")
    masha, user = register(client, email="masha@example.com", name="Маша")
    r = client.patch(f"/api/admin/users/{user['id']}", headers=admin, json={"password": "new-pass-phrase-77"})
    assert r.status_code == 200
    assert client.get("/api/auth/me", headers=masha).status_code == 401
    assert login(client, email="masha@example.com", password="new-pass-phrase-77").status_code == 200


# --- лимиты попыток ---
def test_login_bruteforce_is_throttled(client, rate_limited):
    register(client)
    codes = [login(client, password=f"guess-{i}").status_code for i in range(11)]
    assert codes[:10] == [401] * 10
    assert codes[10] == 429
    r = login(client)  # даже верный пароль: адрес временно заблокирован
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0


def test_login_limit_per_email_survives_changing_ip(client, rate_limited):
    """Распределённый перебор одной почты с разных адресов тоже упирается в лимит."""
    register(client)
    for i in range(20):
        login(client, password=f"guess-{i}")
        limiter._hits.pop("login-ip:testclient", None)  # будто каждая попытка с нового адреса
    assert login(client).status_code == 429
    assert login(client, email="other@example.com").status_code == 401  # другие почты не страдают


def test_registration_is_throttled(client, rate_limited):
    codes = [
        client.post("/api/auth/register", json={"email": f"u{i}@example.com", "name": "U", "password": "kapsula-secret-123", "consent": True}).status_code
        for i in range(11)
    ]
    assert codes[:10] == [201] * 10 and codes[10] == 429


def test_account_deletion_password_cannot_be_guessed(client, rate_limited):
    """С украденным токеном нельзя перебором пароля стереть чужой аккаунт."""
    h, _ = register(client)
    codes = [client.request("DELETE", "/api/auth/me", headers=h, json={"password": f"g{i}"}).status_code for i in range(6)]
    assert codes[:5] == [403] * 5 and codes[5] == 429
    assert client.get("/api/auth/me", headers=h).status_code == 200


def test_account_deletion_with_too_long_password_is_not_a_crash(client):
    h, _ = register(client)
    assert client.request("DELETE", "/api/auth/me", headers=h, json={"password": "я" * 100}).status_code == 403


def test_invite_codes_cannot_be_enumerated(client, rate_limited):
    codes = [client.get(f"/api/invites/AAAA{i:04d}").status_code for i in range(31)]
    assert codes[:30] == [404] * 30 and codes[30] == 429


def test_barcode_lookups_are_throttled_per_user(client, owner, rate_limited):
    h, _, family_id = owner
    codes = [client.get("/api/products/4605077018932", headers=h).status_code for _ in range(61)]
    assert 429 not in codes[:60] and codes[60] == 429


# --- ограничения на размер полей (Postgres на длинной строке падал с 500) ---
@pytest.mark.parametrize("field,value", [
    ("form", "т" * 61),
    ("dosage", "1" * 61),
    ("manufacturer", "x" * 201),
    ("notes", "x" * 5001),
    ("unit", ""),
])
def test_medicine_fields_are_length_limited(client, owner, field, value):
    h, _, family_id = owner
    r = client.post(f"/api/families/{family_id}/medicines", headers=h, json={"name": "Нурофен", field: value})
    assert r.status_code == 422


def test_package_fields_are_length_limited(client, owner):
    h, _, family_id = owner
    r = client.post(
        f"/api/families/{family_id}/medicines", headers=h,
        json={"name": "Нурофен", "packages": [{"quantity": 1, "location": "x" * 101}]},
    )
    assert r.status_code == 422


def test_search_query_is_length_limited(client, owner):
    h, _, family_id = owner
    assert client.get(f"/api/families/{family_id}/medicines", headers=h, params={"q": "x" * 201}).status_code == 422


# --- заголовки ---
def test_security_headers(client):
    r = client.get("/api/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Referrer-Policy"] == "same-origin"
    assert "camera=(self)" in r.headers["Permissions-Policy"]
    csp = r.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp and "'unsafe-eval'" not in csp
    assert r.headers["Cache-Control"] == "no-store"

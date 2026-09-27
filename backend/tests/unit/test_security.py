"""Пароли, JWT-токены и коды приглашений."""

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.config import get_settings
from app.security import ALGORITHM, create_token, decode_token, hash_password, new_invite_code, verify_password


def test_password_hash_roundtrip():
    h = hash_password("secret123")
    assert h != "secret123" and h.startswith("$2")
    assert verify_password("secret123", h)
    assert not verify_password("Secret123", h)


def test_same_password_gets_different_salt():
    assert hash_password("secret123") != hash_password("secret123")


def test_unicode_password():
    h = hash_password("пароль🙂")
    assert verify_password("пароль🙂", h) and not verify_password("пароль", h)


def test_token_roundtrip():
    assert decode_token(create_token(42)) == (42, 0)
    assert decode_token(create_token(42, token_version=3)) == (42, 3)


def test_token_expires_after_ttl():
    token = create_token(1)
    exp = jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM])["exp"]
    days = (datetime.fromtimestamp(exp, timezone.utc) - datetime.now(timezone.utc)).days
    assert days in (get_settings().token_ttl_days - 1, get_settings().token_ttl_days)


def _forge(payload: dict, key: str | None = None, alg: str = ALGORITHM) -> str:
    return jwt.encode(payload, key or get_settings().secret_key, algorithm=alg)


@pytest.mark.parametrize("token", [
    "",
    "not-a-token",
    _forge({"sub": "1", "exp": datetime.now(timezone.utc) - timedelta(seconds=1)}),           # истёк
    _forge({"sub": "1"}, key="another-secret-another-secret-another-secret"),                   # чужой ключ
    _forge({"exp": datetime.now(timezone.utc) + timedelta(days=1)}),                           # нет sub
    _forge({"sub": "abc", "exp": datetime.now(timezone.utc) + timedelta(days=1)}),             # sub не число
    _forge({"sub": "1"}, alg="HS512"),                                                          # другой алгоритм
    _forge({"sub": "1"}),                                                                       # без срока — вечный токен
    _forge({"sub": "1", "tv": "x", "exp": datetime.now(timezone.utc) + timedelta(days=1)}),    # версия не число
])
def test_invalid_tokens_are_rejected(token):
    assert decode_token(token) is None


def test_unsigned_token_is_rejected():
    """Классическая атака alg=none: токен без подписи не должен приниматься."""
    token = jwt.encode({"sub": "1"}, None, algorithm="none")
    assert decode_token(token) is None


def test_invite_code_shape():
    codes = {new_invite_code() for _ in range(200)}
    assert len(codes) == 200  # коллизии на 200 штуках практически невозможны
    for c in codes:
        assert len(c) == 8
        assert not set(c) & set("01IO")  # без похожих символов

"""Пробный Плюс: выдаётся один раз при первой регистрации (подтверждении почты), срок задаёт админ."""
from datetime import datetime, timedelta, timezone

import pytest

from app import mailer
from app.config import get_settings
from app.models import User
from app.plans import grant_trial
from tests.conftest import register
from tests.integration.test_email_verification import outbox, token_from  # noqa: F401


@pytest.fixture(autouse=True)
def trial_on(monkeypatch):
    monkeypatch.setattr("app.plans.DEFAULT_TRIAL_DAYS", 5)


@pytest.fixture
def row(session_factory):
    """Строка пользователя из базы; сессия закрывается сразу: открытая транзакция на Postgres повисла бы на сносе схемы."""
    def get(email):
        with session_factory() as s:
            return s.query(User).filter(User.email == email).one()
    return get


def test_trial_days_default_and_admin_can_change(client):
    h, _ = register(client)
    assert client.get("/api/admin/billing", headers=h).json()["trial_days"] == 5
    assert client.get("/api/auth/access").json()["trial_days"] == 5
    r = client.put("/api/admin/billing", headers=h, json={"enabled": False, "trial_days": 14})
    assert r.json()["trial_days"] == 14
    assert client.put("/api/admin/billing", headers=h, json={"trial_days": 91}).status_code == 422
    assert client.put("/api/admin/billing", headers=h, json={"trial_days": -1}).status_code == 422


def test_trial_granted_on_register_without_email_check(client, row):
    h, me = register(client, "new@example.com")
    u = row("new@example.com")
    assert u.plan == "plus" and u.trial_granted_at is not None
    left = u.plus_until.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)
    assert timedelta(days=4, hours=23) < left <= timedelta(days=5)
    assert me["plus_active"] is True


def test_trial_zero_days_means_off(client, row):
    h, _ = register(client)
    client.put("/api/admin/billing", headers=h, json={"trial_days": 0})
    register(client, "b@example.com")
    u = row("b@example.com")
    assert u.plan == "free" and u.trial_granted_at is None


def test_trial_given_after_email_confirmation_only_once(client, outbox, row, session_factory):
    h, u = register(client, "c@example.com")
    assert u["plus_active"] is False  # до подтверждения почты подарка нет
    token = token_from(outbox[0])
    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 204
    u = row("c@example.com")
    assert u.plan == "plus" and u.trial_granted_at is not None
    # Подарок уже использован: после окончания второй раз не выдаётся.
    with session_factory() as db:
        user = db.get(User, u.id)
        user.plan, user.plus_until = "free", None
        db.commit()
        assert grant_trial(db, user) is False


def test_trial_not_granted_to_paid_plus(client, session_factory):
    h, u = register(client)
    # админ (первый аккаунт) получил подарок при регистрации; платный Плюс бессрочно не перезаписывается
    with session_factory() as db:
        user = db.get(User, u["id"])
        user.trial_granted_at = None
        user.plan, user.plus_until = "plus", None
        assert grant_trial(db, user) is False
        assert user.plus_until is None


def test_access_exposes_listed_price_while_billing_off(client):
    h, _ = register(client)
    client.put("/api/admin/billing", headers=h, json={"enabled": False, "price_month": 199, "price_year": 1990, "trial_days": 5})
    a = client.get("/api/auth/access").json()
    assert a["price_month"] is None and a["billing_enabled"] is False  # лендинг цену не рекламирует
    assert a["listed_price_month"] == 199 and a["listed_price_year"] == 1990  # /plus её показывает

"""Пробный Плюс: выдаётся один раз при первой регистрации (подтверждении почты), срок задаёт админ."""
from datetime import datetime, timedelta, timezone

import pytest

from app import mailer
from app.config import get_settings
from app.db import get_db
from app.main import app
from app.models import User
from tests.conftest import register
from tests.integration.test_email_verification import outbox, token_from  # noqa: F401


@pytest.fixture(autouse=True)
def trial_on(monkeypatch):
    monkeypatch.setattr("app.plans.DEFAULT_TRIAL_DAYS", 5)


def user_row(client, email):
    db = next(app.dependency_overrides[get_db]())
    return db.query(User).filter(User.email == email).one()


def test_trial_days_default_and_admin_can_change(client):
    h, _ = register(client)
    assert client.get("/api/admin/billing", headers=h).json()["trial_days"] == 5
    assert client.get("/api/auth/access").json()["trial_days"] == 5
    r = client.put("/api/admin/billing", headers=h, json={"enabled": False, "trial_days": 14})
    assert r.json()["trial_days"] == 14
    assert client.put("/api/admin/billing", headers=h, json={"trial_days": 91}).status_code == 422
    assert client.put("/api/admin/billing", headers=h, json={"trial_days": -1}).status_code == 422


def test_trial_granted_on_register_without_email_check(client):
    h, u = register(client, "new@example.com")
    row = user_row(client, "new@example.com")
    assert row.plan == "plus" and row.trial_granted_at is not None
    left = row.plus_until.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)
    assert timedelta(days=4, hours=23) < left <= timedelta(days=5)
    assert u["plus_active"] is True


def test_trial_zero_days_means_off(client):
    h, _ = register(client)
    client.put("/api/admin/billing", headers=h, json={"trial_days": 0})
    register(client, "b@example.com")
    row = user_row(client, "b@example.com")
    assert row.plan == "free" and row.trial_granted_at is None


def test_trial_given_after_email_confirmation_only_once(client, outbox):
    h, u = register(client, "c@example.com")
    assert u["plus_active"] is False  # до подтверждения почты подарка нет
    token = token_from(outbox[0])
    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 204
    row = user_row(client, "c@example.com")
    assert row.plan == "plus" and row.trial_granted_at is not None
    # Подарок уже использован: после окончания второй раз не выдаётся.
    row.plan, row.plus_until = "free", None
    db = next(app.dependency_overrides[get_db]())
    db.merge(row)
    db.commit()
    from app.plans import grant_trial
    assert grant_trial(db, db.get(User, row.id)) is False


def test_trial_not_granted_to_paid_plus(client):
    h, u = register(client)
    # админ (первый аккаунт) получил подарок при регистрации; платный Плюс бессрочно не перезаписывается
    db = next(app.dependency_overrides[get_db]())
    row = db.get(User, u["id"])
    row.trial_granted_at = None
    row.plan, row.plus_until = "plus", None
    from app.plans import grant_trial
    assert grant_trial(db, row) is False
    assert row.plus_until is None

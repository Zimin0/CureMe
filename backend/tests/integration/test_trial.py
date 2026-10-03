"""Пробный Плюс: выдаётся один раз при первой регистрации (подтверждении почты), срок задаёт админ."""
from datetime import datetime, timedelta, timezone

import pytest

from app import mailer
from app.config import get_settings
from app.models import Household, User
from app.plans import grant_trial
from tests.conftest import check_household_invariants, register
from tests.integration.test_email_verification import outbox, code_from  # noqa: F401


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


@pytest.fixture
def house(session_factory):
    """Семья человека по почте: тариф и пробный срок лежат на ней."""
    def get(email):
        with session_factory() as s:
            return s.query(User).filter(User.email == email).one().household
    return get


def test_trial_days_default_and_admin_can_change(client):
    h, _ = register(client)
    assert client.get("/api/admin/billing", headers=h).json()["trial_days"] == 5
    assert client.get("/api/auth/access").json()["trial_days"] == 5
    r = client.put("/api/admin/billing", headers=h, json={"enabled": False, "trial_days": 14})
    assert r.json()["trial_days"] == 14
    assert client.put("/api/admin/billing", headers=h, json={"trial_days": 91}).status_code == 422
    assert client.put("/api/admin/billing", headers=h, json={"trial_days": -1}).status_code == 422


def test_r07_t1_trial_granted_to_personal_family_on_register_without_email_check(client, row, house):
    h, me = register(client, "new@example.com")
    u, fam = row("new@example.com"), house("new@example.com")
    assert fam.plan == "plus" and fam.plus_is_trial is True and u.trial_granted_at is not None
    left = fam.plus_until.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)
    assert timedelta(days=4, hours=23) < left <= timedelta(days=5)
    assert me["plus_active"] is True


def test_trial_zero_days_means_off(client, row, house):
    h, _ = register(client)
    client.put("/api/admin/billing", headers=h, json={"trial_days": 0})
    register(client, "b@example.com")
    u = row("b@example.com")
    assert house("b@example.com").plan == "free" and u.trial_granted_at is None


def test_r07_t5_trial_given_after_email_confirmation_only_once(client, outbox, row, house, session_factory):
    h, u = register(client, "c@example.com")
    assert u["plus_active"] is False  # до подтверждения почты подарка нет
    code = code_from(outbox[0])
    assert client.post("/api/auth/verify-email", headers=h, json={"code": code}).status_code == 204
    u, fam = row("c@example.com"), house("c@example.com")
    assert fam.plan == "plus" and u.trial_granted_at is not None
    # Подарок уже использован: после окончания второй раз не выдаётся.
    with session_factory() as db:
        user = db.get(User, u.id)
        user.household.plan, user.household.plus_until = "free", None
        db.commit()
        assert grant_trial(db, user) is False


def test_trial_not_granted_to_paid_plus(client, session_factory):
    h, u = register(client)
    # админ (первый аккаунт) получил подарок при регистрации; платный Плюс бессрочно не перезаписывается
    with session_factory() as db:
        user = db.get(User, u["id"])
        user.trial_granted_at = None
        user.household.plan, user.household.plus_until = "plus", None
        assert grant_trial(db, user) is False
        assert user.household.plus_until is None


def test_access_exposes_listed_price_while_billing_off(client):
    h, _ = register(client)
    client.put("/api/admin/billing", headers=h, json={"enabled": False, "price_month": 199, "price_year": 1990, "trial_days": 5})
    a = client.get("/api/auth/access").json()
    assert a["price_month"] is None and a["billing_enabled"] is False  # лендинг цену не рекламирует
    assert a["listed_price_month"] == 199 and a["listed_price_year"] == 1990  # /plus её показывает


def code_of(client, h):
    return client.get(f"/api/families/{client.get('/api/auth/me', headers=h).json()['families'][0]['id']}", headers=h).json()["invite_code"]


def test_r07_t2_invited_registration_gets_no_trial_and_brings_none(client, row, house, session_factory):
    h, _ = register(client, "owner@example.com", "Владелец")
    before = house("owner@example.com").plus_until
    register(client, "kid@example.com", "Сын", invite=code_of(client, h))
    assert row("kid@example.com").trial_granted_at is None  # приглашённому подарок не даётся
    assert house("kid@example.com").plus_until == before  # и семье Плюс не прибавился
    check_household_invariants(session_factory)


def test_r07_t3_trial_does_not_move_to_another_family(client, row, house, session_factory):
    h, _ = register(client, "owner@example.com", "Владелец")
    owner_until = house("owner@example.com").plus_until
    hn, _ = register(client, "new@example.com", "Новичок")  # у него свой пробный
    assert house("new@example.com").plus_is_trial is True
    assert client.post("/api/families/join", headers=hn, json={"code": code_of(client, h)}).status_code == 200
    assert house("new@example.com").plus_until == owner_until  # чужой семье Плюс не прибавился
    with session_factory() as db:
        assert db.query(Household).count() == 1  # его личная семья с пробным растворилась
    check_household_invariants(session_factory)


def test_r07_t4_leaving_does_not_return_the_trial(client, row, house, session_factory):
    h, _ = register(client, "owner@example.com", "Владелец")
    hn, new = register(client, "new@example.com", "Новичок")  # получил пробный и вступил в чужую семью
    f = client.get("/api/auth/me", headers=h).json()["families"][0]["id"]
    assert client.post("/api/families/join", headers=hn, json={"code": code_of(client, h)}).status_code == 200
    granted = row("new@example.com").trial_granted_at
    assert client.delete(f"/api/families/{f}/members/{new['id']}", headers=hn).status_code == 204
    assert house("new@example.com").plan == "free"  # у новой личной семьи пробного нет
    assert row("new@example.com").trial_granted_at == granted  # пометка о подарке не обнуляется
    with session_factory() as db:
        assert grant_trial(db, db.get(User, new["id"])) is False
    check_household_invariants(session_factory)

"""Тарифы «Бесплатный» и «Плюс»: переключатель в админке, лимиты и проверки из plans.py."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app import plans
from app.db import get_db
from app.models import Family, User
from tests.conftest import check_household_invariants, fid, grant_plus, invite_of, register

REAL_NEW_TERMS_FROM = plans.NEW_TERMS_FROM  # conftest сдвигает дату в прошлое для всех тестов; настоящую читаем при импорте

# Потолки Плюса действуют всегда, даже пока платная версия выключена (R02, R03); остальные лимиты снимаются.
PLUS_LIMITS = {"members": plans.PLUS_MEMBERS_MAX, "medicines": None, "own_families": plans.PLUS_OWN_FAMILIES_MAX, "history_days": None}


@pytest.fixture
def admin(client):
    """Первый аккаунт — администратор и владелец своей семьи."""
    h, u = register(client)
    return h, fid(u)


def enable_billing(client, h, on=True):
    r = client.put("/api/admin/billing", headers=h, json={"enabled": on, "trial_days": 0})
    assert r.status_code == 200 and r.json()["enabled"] is on


def test_billing_is_off_by_default_and_everything_is_open(client, admin):
    h, f = admin
    assert client.get("/api/admin/billing", headers=h).json()["enabled"] is False
    p = client.get(f"/api/families/{f}/plan", headers=h).json()
    assert p["plan"] == "free" and p["plus_active"] is False
    assert p["billing_enabled"] is False and p["has_plus"] is True
    assert p["limits"] == PLUS_LIMITS
    assert all(x["available"] for x in p["features"])


def test_free_family_gets_limits_when_billing_on(client, admin):
    h, f = admin
    enable_billing(client, h)
    client.post(f"/api/families/{f}/medicines", headers=h, json={"name": "Нурофен"})
    p = client.get(f"/api/families/{f}/plan", headers=h).json()
    assert p["has_plus"] is False
    assert p["limits"] == plans.FREE_LIMITS == p["free_limits"]
    assert p["usage"] == {"members": 1, "medicines": 1}
    assert {x["key"] for x in p["features"]} == set(plans.FEATURES)
    assert not any(x["available"] for x in p["features"])


def owner_id(client, h, f):
    return next(x for x in client.get("/api/admin/families", headers=h).json() if x["id"] == f)["owner_id"]


def test_admin_turns_plus_on_with_and_without_end_date(client, admin):
    h, f = admin
    enable_billing(client, h)
    until = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    r = grant_plus(client, h, f, until=until)
    assert r.json()["plan"] == "plus" and r.json()["plus_active"] is True and r.json()["plus_until"]
    p = client.get(f"/api/families/{f}/plan", headers=h).json()
    assert p["has_plus"] and p["limits"] == PLUS_LIMITS
    assert p["owner_name"] == "Никита"

    fam = next(x for x in client.get("/api/admin/families", headers=h).json() if x["id"] == f)
    assert fam["plan"] == "plus" and fam["plus_active"]

    r = grant_plus(client, h, f)
    assert r.json()["plus_until"] is None and r.json()["plus_active"] is True  # бессрочно

    r = grant_plus(client, h, f, plan="free", until=until)
    assert r.json()["plan"] == "free" and r.json()["plus_until"] is None and not r.json()["plus_active"]


def test_expired_plus_works_as_free(client, admin):
    h, f = admin
    enable_billing(client, h)
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    assert grant_plus(client, h, f, until=past).json()["plus_active"] is False
    assert client.get(f"/api/families/{f}/plan", headers=h).json()["has_plus"] is False


def test_unknown_plan_is_rejected(client, admin):
    h, f = admin
    uid = owner_id(client, h, f)
    assert client.put(f"/api/admin/users/{uid}/plan", headers=h, json={"plan": "gold"}).status_code == 422


def test_second_cabinet_of_paying_owner_has_plus(client, admin):
    """Плюс на семье: новая аптечка сразу под Плюсом, а не отдельная «бесплатная семья»."""
    h, f = admin
    enable_billing(client, h)
    grant_plus(client, h, f)
    second = client.post("/api/families", headers=h, json={"name": "С собой"}).json()["id"]
    p = client.get(f"/api/families/{second}/plan", headers=h).json()
    assert p["plus_active"] and p["has_plus"] and p["limits"] == PLUS_LIMITS
    fams = {x["id"]: x for x in client.get("/api/admin/families", headers=h).json()}
    assert fams[second]["plus_active"] and fams[second]["owner_id"] == fams[f]["owner_id"]


def test_r05_plus_given_to_any_person_applies_to_the_whole_family(client, admin, session_factory):
    """Тариф у семьи, а не у человека: Плюс, выданный любому её человеку, получают все и все аптечки (R05)."""
    h, f = admin
    enable_billing(client, h)
    code = client.get(f"/api/families/{f}", headers=h).json()["invite_code"]
    h2, u2 = register(client, "payer@example.com", "Платящий", invite=code)
    own = client.post("/api/families", headers=h2, json={"name": "Своя"}).json()["id"]
    assert client.get(f"/api/families/{f}/plan", headers=h2).json()["has_plus"] is False
    assert client.put(f"/api/admin/users/{u2['id']}/plan", headers=h, json={"plan": "plus"}).status_code == 200
    for hh in (h, h2):
        assert client.get(f"/api/families/{f}/plan", headers=hh).json()["has_plus"] is True
        assert client.get(f"/api/families/{own}/plan", headers=hh).json()["has_plus"] is True
    check_household_invariants(session_factory)


def test_plus_caps_own_cabinets(client, admin):
    h, f = admin
    enable_billing(client, h)
    grant_plus(client, h, f)
    for i in range(plans.PLUS_OWN_FAMILIES_MAX - 1):
        assert client.post("/api/families", headers=h, json={"name": f"Аптечка {i}"}).status_code == 201
    me = client.get("/api/auth/me", headers=h).json()
    assert me["own_families_left"] == 0 and me["plus_active"] is True
    r = client.post("/api/families", headers=h, json={"name": "Лишняя"})
    assert r.status_code == 409 and plans.PLUS_HEADER not in r.headers  # не шторка «купите Плюс»


def test_member_sees_plan_but_cannot_change_it(client, admin):
    h, f = admin
    code = client.get(f"/api/families/{f}", headers=h).json()["invite_code"]
    h2, _ = register(client, "mom@example.com", "Мама", invite=code)
    assert client.get(f"/api/families/{f}/plan", headers=h2).status_code == 200
    assert client.put(f"/api/admin/users/{owner_id(client, h, f)}/plan", headers=h2, json={"plan": "plus"}).status_code == 403


# --- помощники для других модулей ----------------------------------------------

def test_check_limit_and_require_plus(client, admin, db):
    h, f = admin
    family = db.get(Family, f)
    plans.check_limit(db, family, "medicines", used=1000)  # платная версия выключена — лимитов нет
    plans.require_plus(db, family, "export_pdf")

    enable_billing(client, h)
    db.expire_all()
    plans.check_limit(db, family, "medicines", used=59)
    with pytest.raises(Exception) as e:
        plans.check_limit(db, family, "medicines", used=60)
    assert e.value.status_code == 402
    assert e.value.headers == {plans.PLUS_HEADER: "no_limits"}
    assert "60" in e.value.detail

    with pytest.raises(Exception) as e:
        plans.require_plus(db, family, "export_pdf")
    assert e.value.status_code == 402 and e.value.headers[plans.PLUS_HEADER] == "export_pdf"
    with pytest.raises(ValueError):
        plans.require_plus(db, family, "unknown")

    since = plans.history_since(db, family)
    assert since is not None and abs((datetime.now(timezone.utc) - since) - timedelta(days=30)) < timedelta(minutes=1)

    family.household.plan = "plus"
    db.commit()
    assert plans.history_since(db, family) is None
    plans.check_limit(db, family, "medicines", used=1000)


def test_own_families_left(client, admin, db):
    h, _ = admin
    me = client.get("/api/auth/me", headers=h).json()
    assert plans.own_families_left(db, me["id"]) is None
    enable_billing(client, h)
    db.expire_all()
    assert plans.own_families_left(db, me["id"]) == 0  # одна своя уже есть
    db.get(User, me["id"]).household.plan = "plus"
    db.commit()
    assert plans.own_families_left(db, me["id"]) == plans.PLUS_OWN_FAMILIES_MAX - 1


def test_plus_feature_dependency_returns_402_with_header(client, admin, session_factory):
    h, f = admin
    app = FastAPI()

    @app.get("/api/families/{family_id}/secret")
    def secret(family: Family = Depends(plans.plus_feature("reminders"))):
        return {"family": family.id}

    def override():
        s = session_factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    c = TestClient(app)
    assert c.get(f"/api/families/{f}/secret", headers=h).json() == {"family": f}
    enable_billing(client, h)
    r = c.get(f"/api/families/{f}/secret", headers=h)
    assert r.status_code == 402 and r.headers[plans.PLUS_HEADER] == "reminders"
    assert "Плюс" in r.json()["detail"]
    with pytest.raises(ValueError):
        plans.plus_feature("unknown")


def test_admin_sets_plus_price_and_family_sees_it(client, admin):
    h, f = admin
    assert client.get(f"/api/families/{f}/plan", headers=h).json()["price_month"] is None
    r = client.put("/api/admin/billing", headers=h, json={"enabled": False, "price_month": 149, "price_year": 990, "trial_days": 0, "plus_theme": True})
    assert r.status_code == 200
    assert client.get("/api/admin/billing", headers=h).json() == {"enabled": False, "price_month": 149, "price_year": 990, "trial_days": 0, "plus_theme": True}
    p = client.get(f"/api/families/{f}/plan", headers=h).json()
    assert (p["price_month"], p["price_year"]) == (149, 990)
    # переключатель не стирает цену, если фронтенд прислал её обратно; пустая цена убирается
    client.put("/api/admin/billing", headers=h, json={"enabled": True, "price_month": 149, "price_year": None, "trial_days": 0})
    p = client.get(f"/api/families/{f}/plan", headers=h).json()
    assert p["billing_enabled"] and p["price_month"] == 149 and p["price_year"] is None


@pytest.mark.parametrize("body", [{"price_month": 0}, {"price_month": -5}, {"price_year": 10_000_000}, {"price_month": "дорого"}])
def test_bad_price_is_rejected(client, admin, body):
    h, _ = admin
    assert client.put("/api/admin/billing", headers=h, json={"enabled": False, **body}).status_code == 422


# --- переходный период новой редакции Соглашения (п. 11.2: 10 дней до вступления в силу) -----------

def join_family(client, h, f, count):
    """Добавляет в семью `count` человек: код одноразовый, для каждого свой; возвращает заголовки последнего."""
    last = None
    for i in range(count):
        last, _ = register(client, f"member{i}@example.com", f"Человек {i}", invite=invite_of(client, h, f))
    return last


def fifth_tries_to_join(client, h, f):
    code = invite_of(client, h, f)
    h5, _ = register(client, "fifth@example.com", "Пятый")
    return client.post("/api/families/join", headers=h5, json={"code": code})


def test_r02_transition_free_family_keeps_four_people_until_new_terms(client, admin, monkeypatch, session_factory, db):
    """До 13 октября действует прежний предел: в бесплатной семье 4 человека, аптечек по-прежнему не больше 3."""
    h, f = admin
    monkeypatch.setattr(plans, "NEW_TERMS_FROM", datetime.now(timezone.utc) + timedelta(days=5))
    enable_billing(client, h)
    join_family(client, h, f, 3)
    p = client.get(f"/api/families/{f}/plan", headers=h).json()
    assert p["limits"]["members"] == p["free_limits"]["members"] == plans.OLD_FREE_MEMBERS == 4
    assert p["usage"]["members"] == 4
    r = fifth_tries_to_join(client, h, f)
    assert r.status_code == 402 and r.headers[plans.PLUS_HEADER] == "no_limits"
    assert plans.limit_for(db, None, "own_families", people=4) == plans.FREE_CABINETS_MAX == 3
    check_household_invariants(session_factory)


def test_r02_transition_four_people_stay_after_new_terms(client, admin, monkeypatch):
    """С 13 октября предел 3, но семью из 4 человек не трогаем: никого не исключаем, новых не принимаем."""
    h, f = admin
    monkeypatch.setattr(plans, "NEW_TERMS_FROM", datetime.now(timezone.utc) + timedelta(days=5))
    enable_billing(client, h)
    last = join_family(client, h, f, 3)
    monkeypatch.setattr(plans, "NEW_TERMS_FROM", datetime.now(timezone.utc) - timedelta(seconds=1))
    p = client.get(f"/api/families/{f}/plan", headers=h).json()
    assert p["limits"]["members"] == p["free_limits"]["members"] == 3 and p["usage"]["members"] == 4
    assert len(client.get(f"/api/families/{f}", headers=h).json()["members"]) == 4
    assert client.get(f"/api/families/{f}/medicines", headers=last).status_code == 200  # доступ у всех сохранился
    r = fifth_tries_to_join(client, h, f)
    assert r.status_code == 402


def test_free_members_limit_switches_at_new_terms_date(monkeypatch):
    monkeypatch.setattr(plans, "NEW_TERMS_FROM", REAL_NEW_TERMS_FROM)
    assert plans.free_members_limit(REAL_NEW_TERMS_FROM - timedelta(seconds=1)) == 4
    assert REAL_NEW_TERMS_FROM == datetime(2026, 10, 12, 21, 0, tzinfo=timezone.utc)  # 13 октября 00:00 МСК, как в Соглашении
    assert plans.free_members_limit(REAL_NEW_TERMS_FROM) == 3  # настройка теста: новая редакция уже действует
    assert plans.OLD_FREE_MEMBERS == 4


def test_plus_theme_switch_is_on_by_default_and_admin_can_turn_it_off(client, admin):
    h, f = admin
    assert client.get("/api/admin/billing", headers=h).json()["plus_theme"] is True
    assert client.get(f"/api/families/{f}/plan", headers=h).json()["plus_theme"] is True
    r = client.put("/api/admin/billing", headers=h, json={"enabled": False, "trial_days": 0, "plus_theme": False})
    assert r.status_code == 200 and r.json()["plus_theme"] is False
    assert client.get(f"/api/families/{f}/plan", headers=h).json()["plus_theme"] is False
    r = client.put("/api/admin/billing", headers=h, json={"enabled": False, "trial_days": 0, "plus_theme": True})
    assert client.get(f"/api/families/{f}/plan", headers=h).json()["plus_theme"] is True

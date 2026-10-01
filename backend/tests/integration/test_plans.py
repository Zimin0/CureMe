"""Тарифы «Бесплатный» и «Плюс»: переключатель в админке, лимиты и проверки из plans.py."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app import plans
from app.db import get_db
from app.models import Family, User
from tests.conftest import fid, grant_plus, register


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
    assert all(v is None for v in p["limits"].values())
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
    assert p["has_plus"] and all(v is None for v in p["limits"].values())
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
    """Плюс на аккаунте: новая аптечка платящего владельца сразу под Плюсом, а не отдельная «бесплатная семья»."""
    h, f = admin
    enable_billing(client, h)
    grant_plus(client, h, f)
    second = client.post("/api/families", headers=h, json={"name": "С собой"}).json()["id"]
    p = client.get(f"/api/families/{second}/plan", headers=h).json()
    assert p["plus_active"] and p["has_plus"] and all(v is None for v in p["limits"].values())
    fams = {x["id"]: x for x in client.get("/api/admin/families", headers=h).json()}
    assert fams[second]["plus_active"] and fams[second]["owner_id"] == fams[f]["owner_id"]


def test_paying_co_owner_does_not_give_plus_to_someone_elses_family(client, admin):
    """Платящего добавили в чужую семью, даже сделали владельцем: чужой аптечке Плюс не даёт."""
    h, f = admin  # администратор и главный владелец, без Плюса
    enable_billing(client, h)
    code = client.get(f"/api/families/{f}", headers=h).json()["invite_code"]
    h2, u2 = register(client, "payer@example.com", "Платящий", invite=code)
    assert client.put(f"/api/admin/users/{u2['id']}/plan", headers=h, json={"plan": "plus"}).status_code == 200
    own = client.post("/api/families", headers=h2, json={"name": "Своя"}).json()["id"]
    assert client.patch(f"/api/families/{f}/members/{u2['id']}", headers=h, json={"role": "owner"}).status_code == 200
    p = client.get(f"/api/families/{f}/plan", headers=h2).json()
    assert p["plus_active"] is False and p["has_plus"] is False
    assert client.get(f"/api/families/{own}/plan", headers=h2).json()["has_plus"] is True


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

    family.memberships[0].user.plan = "plus"
    db.commit()
    assert plans.history_since(db, family) is None
    plans.check_limit(db, family, "members", used=100)


def test_own_families_left(client, admin, db):
    h, _ = admin
    me = client.get("/api/auth/me", headers=h).json()
    assert plans.own_families_left(db, me["id"]) is None
    enable_billing(client, h)
    db.expire_all()
    assert plans.own_families_left(db, me["id"]) == 0  # одна своя уже есть
    db.get(User, me["id"]).plan = "plus"
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
    r = client.put("/api/admin/billing", headers=h, json={"enabled": False, "price_month": 149, "price_year": 990, "trial_days": 0})
    assert r.status_code == 200
    assert client.get("/api/admin/billing", headers=h).json() == {"enabled": False, "price_month": 149, "price_year": 990, "trial_days": 0}
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

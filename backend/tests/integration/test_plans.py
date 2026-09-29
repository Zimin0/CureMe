"""Тарифы «Бесплатный» и «Плюс»: переключатель в админке, лимиты и проверки из plans.py."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app import plans
from app.db import get_db
from app.models import Family
from tests.conftest import fid, register


@pytest.fixture
def admin(client):
    """Первый аккаунт — администратор и владелец своей семьи."""
    h, u = register(client)
    return h, fid(u)


def enable_billing(client, h, on=True):
    r = client.put("/api/admin/billing", headers=h, json={"enabled": on})
    assert r.status_code == 200 and r.json() == {"enabled": on}


def test_billing_is_off_by_default_and_everything_is_open(client, admin):
    h, f = admin
    assert client.get("/api/admin/billing", headers=h).json() == {"enabled": False}
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


def test_admin_turns_plus_on_with_and_without_end_date(client, admin):
    h, f = admin
    enable_billing(client, h)
    until = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    r = client.put(f"/api/admin/families/{f}/plan", headers=h, json={"plan": "plus", "plus_until": until})
    assert r.status_code == 200
    assert r.json()["plan"] == "plus" and r.json()["plus_active"] is True and r.json()["plus_until"]
    p = client.get(f"/api/families/{f}/plan", headers=h).json()
    assert p["has_plus"] and all(v is None for v in p["limits"].values())

    fam = next(x for x in client.get("/api/admin/families", headers=h).json() if x["id"] == f)
    assert fam["plan"] == "plus" and fam["plus_active"]

    r = client.put(f"/api/admin/families/{f}/plan", headers=h, json={"plan": "plus"})
    assert r.json()["plus_until"] is None and r.json()["plus_active"] is True  # бессрочно

    r = client.put(f"/api/admin/families/{f}/plan", headers=h, json={"plan": "free", "plus_until": until})
    assert r.json()["plan"] == "free" and r.json()["plus_until"] is None and not r.json()["plus_active"]


def test_expired_plus_works_as_free(client, admin):
    h, f = admin
    enable_billing(client, h)
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    r = client.put(f"/api/admin/families/{f}/plan", headers=h, json={"plan": "plus", "plus_until": past})
    assert r.json()["plus_active"] is False
    assert client.get(f"/api/families/{f}/plan", headers=h).json()["has_plus"] is False


def test_unknown_plan_is_rejected(client, admin):
    h, f = admin
    assert client.put(f"/api/admin/families/{f}/plan", headers=h, json={"plan": "gold"}).status_code == 422


def test_member_sees_plan_but_cannot_change_it(client, admin):
    h, f = admin
    code = client.get(f"/api/families/{f}", headers=h).json()["invite_code"]
    h2, _ = register(client, "mom@example.com", "Мама", invite=code)
    assert client.get(f"/api/families/{f}/plan", headers=h2).status_code == 200
    assert client.put(f"/api/admin/families/{f}/plan", headers=h2, json={"plan": "plus"}).status_code == 403


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

    family.plan, family.plus_until = "plus", None
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
    fam = db.get(Family, fid(me))
    fam.plan = "plus"
    db.commit()
    assert plans.own_families_left(db, me["id"]) is None


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

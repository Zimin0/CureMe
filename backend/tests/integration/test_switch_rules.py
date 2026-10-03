"""Кулдаун смены семьи, счётчик смен и вступление человека с оплаченным Плюсом (R08, R09-T6, R10, R11)."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app import households
from app.models import Household, HouseholdEvent, User
from tests.conftest import check_household_invariants, fid, grant_plus, invite_of, register

DAY = timedelta(days=1)


@pytest.fixture
def limits_on(monkeypatch):
    monkeypatch.setattr(households, "SWITCH_COOLDOWN_DAYS", 30)
    monkeypatch.setattr(households, "CHANGES_PER_30D_FREE", 2)
    monkeypatch.setattr(households, "CHANGES_PER_30D_PLUS", 4)


def me(client, h):
    return client.get("/api/auth/me", headers=h).json()


def join(client, h_user, h_owner, f, **extra):
    return client.post("/api/families/join", headers=h_user, json={"code": invite_of(client, h_owner, f), **extra})


def changed_at(session_factory, uid):
    with session_factory() as db:
        return db.get(User, uid).household_changed_at


def back_in_time(session_factory, uid, days):
    with session_factory() as db:
        user = db.get(User, uid)
        user.household_changed_at = datetime.now(timezone.utc) - days * DAY
        db.commit()


@pytest.fixture
def two_families(client, limits_on):
    """Семьи Никиты (X) и Анны (Y) и Боря, который по приглашению зарегистрировался в семье Никиты."""
    hx, x = register(client)
    hy, y = register(client, "anna@example.com", "Анна")
    hb, b = register(client, "bob@example.com", "Боря", invite=invite_of(client, hx, fid(x)))
    return {"hx": hx, "x": x, "hy": hy, "y": y, "hb": hb, "b": b}


def test_r11_t3_registration_by_code_does_not_start_the_cooldown(client, session_factory, two_families):
    w = two_families
    assert changed_at(session_factory, w["b"]["id"]) is None
    assert client.delete(f"/api/families/{fid(w['x'])}/members/{w['b']['id']}", headers=w["hb"]).status_code == 204  # выйти сразу можно


def test_r11_t1_after_a_change_the_next_one_is_refused_with_a_date(client, session_factory, two_families):
    w = two_families
    assert client.delete(f"/api/families/{fid(w['x'])}/members/{w['b']['id']}", headers=w["hb"]).status_code == 204  # выход запустил кулдаун
    assert changed_at(session_factory, w["b"]["id"]) is not None
    r = join(client, w["hb"], w["hy"], fid(w["y"]))
    assert r.status_code == 409 and "раз в 30 дней" in r.json()["detail"] and "по московскому времени" in r.json()["detail"]
    assert me(client, w["hb"])["next_change_at"] is not None  # интерфейс показывает дату
    check_household_invariants(session_factory)


def test_r11_t2_after_31_days_it_is_allowed(client, session_factory, two_families):
    w = two_families
    client.delete(f"/api/families/{fid(w['x'])}/members/{w['b']['id']}", headers=w["hb"])
    back_in_time(session_factory, w["b"]["id"], 31)
    assert join(client, w["hb"], w["hy"], fid(w["y"])).status_code == 200
    assert me(client, w["hb"])["next_change_at"] is not None  # вступление снова запустило кулдаун


def test_r09_t6_leaving_is_refused_while_the_cooldown_runs(client, session_factory, two_families):
    w = two_families
    client.delete(f"/api/families/{fid(w['x'])}/members/{w['b']['id']}", headers=w["hb"])
    back_in_time(session_factory, w["b"]["id"], 31)
    assert join(client, w["hb"], w["hy"], fid(w["y"])).status_code == 200
    r = client.delete(f"/api/families/{fid(w['y'])}/members/{w['b']['id']}", headers=w["hb"])
    assert r.status_code == 409 and "раз в 30 дней" in r.json()["detail"]


def test_r11_t4_kick_does_not_start_the_cooldown(client, session_factory, two_families):
    w = two_families
    assert client.delete(f"/api/families/{fid(w['x'])}/members/{w['b']['id']}", headers=w["hx"]).status_code == 204  # исключил владелец
    assert changed_at(session_factory, w["b"]["id"]) is None
    assert join(client, w["hb"], w["hy"], fid(w["y"])).status_code == 200


def test_r11_t5_family_changes_per_30_days_free_and_plus(client, session_factory, two_families):
    w = two_families
    fx = fid(w["x"])
    with session_factory() as db:
        house = db.get(User, w["x"]["id"]).household
        now = datetime.now(timezone.utc)
        db.add(HouseholdEvent(household_id=house.id, kind="join", detail=households.REGISTRATION, created_at=now))  # не считается
        db.add(HouseholdEvent(household_id=house.id, kind="leave", created_at=now - 40 * DAY))  # старше 30 дней: не считается
        db.add(HouseholdEvent(household_id=house.id, kind="join", created_at=now - 3 * DAY))
        db.commit()
    assert join(client, w["hy"], w["hx"], fx).status_code == 200  # вторая смена: бесплатной семье можно
    hz, _ = register(client, "zoya@example.com", "Зоя")
    r = join(client, hz, w["hx"], fx)
    assert r.status_code == 409 and "смены состава за 30 дней" in r.json()["detail"]
    grant_plus(client, w["hx"], fx)  # с Плюсом в семье разрешено 4, и теперь можно
    assert join(client, hz, w["hx"], fx).status_code == 200
    with session_factory() as db:
        house = db.get(User, w["x"]["id"]).household
        for _ in range(2):  # доводим до четырёх смен
            db.add(HouseholdEvent(household_id=house.id, kind="kick", created_at=datetime.now(timezone.utc)))
        db.commit()
    hq, _ = register(client, "q@example.com", "Ква")
    assert join(client, hq, w["hx"], fx).status_code == 409


def test_r11_t5_admin_may_add_beyond_the_counter(client, session_factory, two_families):
    w = two_families
    with session_factory() as db:
        house = db.get(User, w["x"]["id"]).household
        for _ in range(2):
            db.add(HouseholdEvent(household_id=house.id, kind="join", created_at=datetime.now(timezone.utc)))
        db.commit()
    r = client.post(f"/api/admin/families/{fid(w['x'])}/members", headers=w["hx"], json={"email": "anna@example.com", "role": "member"})
    assert r.status_code == 200  # support-инструмент идёт мимо кулдауна и счётчика (force)


def test_r11_t6_admin_resets_the_cooldown_and_the_journal_remembers(client, session_factory, two_families):
    w = two_families
    client.delete(f"/api/families/{fid(w['x'])}/members/{w['b']['id']}", headers=w["hb"])
    assert join(client, w["hb"], w["hy"], fid(w["y"])).status_code == 409
    assert client.post(f"/api/admin/users/{w['b']['id']}/reset-cooldown", headers=w["hb"]).status_code == 403  # не администратор
    assert client.post(f"/api/admin/users/{w['b']['id']}/reset-cooldown", headers=w["hx"]).status_code == 204
    assert changed_at(session_factory, w["b"]["id"]) is None
    with session_factory() as db:  # запись лежит в журнале его семьи; эта семья исчезнет, если он вступит в другую (R27)
        assert db.scalar(select(HouseholdEvent).where(HouseholdEvent.kind == "cooldown_reset")) is not None
    assert join(client, w["hb"], w["hy"], fid(w["y"])).status_code == 200


# --- вступление человека с оплаченным Плюсом (R08) ---
def paid_person(client, until_days=20):
    """Анна: личная семья с оплаченным Плюсом (выдан администратором на срок) и включённым автопродлением."""
    hy, y = register(client, "anna@example.com", "Анна")
    return hy, y


def grant_days(client, hadmin, f, days):
    until = (datetime.now(timezone.utc) + days * DAY).isoformat()
    grant_plus(client, hadmin, f, until=until)


def plus_until(session_factory, uid):
    with session_factory() as db:
        house = db.get(User, uid).household
        until = house.plus_until
        return house.plan, (until.replace(tzinfo=timezone.utc) if until is not None and until.tzinfo is None else until), house.plus_is_trial


def test_r08_t8_paid_person_cannot_join_and_lose_the_paid_days(client, session_factory):
    hx, x = register(client)
    hy, y = paid_person(client)
    grant_days(client, hx, fid(y), 20)
    r = join(client, hy, hx, fid(x))  # carry_plus не указан
    assert r.status_code == 409 and "оплачен Плюс" in r.json()["detail"] and "перенеся" in r.json()["detail"]
    assert [f["name"] for f in me(client, hy)["families"]] == ["Семья Анна"]  # осталась у себя
    check_household_invariants(session_factory)


def test_r08_t4_t6_paid_days_move_to_the_family_and_limits_follow_plus(client, session_factory):
    hx, x = register(client)
    fx = fid(x)
    for i in range(2):  # в семье Никиты уже трое: четвёртый бесплатному не вместиться
        register(client, f"m{i}@example.com", f"М{i}", invite=invite_of(client, hx, fx))
    hy, y = paid_person(client)
    grant_days(client, hx, fid(y), 20)
    with session_factory() as db:
        owner_y = db.get(User, y["id"])
        owner_y.auto_renew, owner_y.pay_method_id = True, "pm-1"
        db.commit()
    before = datetime.now(timezone.utc)
    r = join(client, hy, hx, fx, carry_plus=True)
    assert r.status_code == 200, r.text
    plan, until, trial = plus_until(session_factory, x["id"])
    assert plan == "plus" and not trial and 19 <= (until - before).days <= 20  # 20 дней семьи Анны перешли к семье Никиты
    assert [f["name"] for f in me(client, hy)["families"]] == ["Семья Никита"]  # личная семья растворилась
    assert len(client.get(f"/api/families/{fx}", headers=hx).json()["members"]) == 4
    with session_factory() as db:
        assert db.get(User, y["id"]).auto_renew is False and db.get(User, y["id"]).pay_method_id is None  # карта отключена
        assert db.scalar(select(HouseholdEvent).where(HouseholdEvent.kind == "plus_carry")) is not None
    check_household_invariants(session_factory)


def test_r08_carried_days_are_added_after_the_family_own_paid_term(client, session_factory):
    hx, x = register(client)
    hy, y = paid_person(client)
    grant_days(client, hx, fid(x), 10)
    grant_days(client, hx, fid(y), 20)
    assert join(client, hy, hx, fid(x), carry_plus=True).status_code == 200
    _, until, _ = plus_until(session_factory, x["id"])
    assert 29 <= (until - datetime.now(timezone.utc)).days <= 30  # 10 + 20


def test_r08_t5_trial_days_are_not_carried(client, session_factory):
    hx, x = register(client)
    hy, y = paid_person(client)
    grant_days(client, hx, fid(y), 20)
    with session_factory() as db:
        db.get(User, y["id"]).household.plus_is_trial = True  # пробный: оплаченным не считается
        db.commit()
    assert join(client, hy, hx, fid(x)).status_code == 200  # ничего выбирать не нужно, пробный пропадает (R07)
    assert plus_until(session_factory, x["id"])[0] == "free"


def test_r08_t7_carry_is_capped_by_13_months(client, session_factory):
    hx, x = register(client)
    hy, y = paid_person(client)
    grant_days(client, hx, fid(x), 380)
    grant_days(client, hx, fid(y), 100)
    r = join(client, hy, hx, fid(x), carry_plus=True)
    assert r.status_code == 409 and "13 месяцев" in r.json()["detail"]
    assert [f["name"] for f in me(client, hy)["families"]] == ["Семья Анна"]


def test_r08_lifetime_plus_cannot_be_carried_and_lifetime_target_cannot_receive(client, session_factory):
    hx, x = register(client)
    hy, y = paid_person(client)
    hz, z = register(client, "zoya@example.com", "Зоя")
    grant_plus(client, hx, fid(y))  # без срока
    r = join(client, hy, hx, fid(x), carry_plus=True)
    assert r.status_code == 409 and "без срока" in r.json()["detail"]
    grant_days(client, hx, fid(z), 10)
    grant_plus(client, hx, fid(x))  # у семьи Никиты Плюс без срока
    r = join(client, hz, hx, fid(x), carry_plus=True)
    assert r.status_code == 409 and "без срока" in r.json()["detail"]

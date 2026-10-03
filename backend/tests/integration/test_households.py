"""Семья и аптечки (docs/household-model/rules-and-cases.md): правила R01–R03, R05, R08–R10, R16, R22, R24 и кейсы BC01–BC03, BC22.

Имя теста повторяет номер правила (`test_r03_t2_...`) или кейса (`test_bc01_...`). Каждый сценарий заканчивается
проверкой инвариантов (R20-T3): у человека одна семья, у семьи один владелец, лимиты, доступ равен людям × аптечкам.
Первый зарегистрированный аккаунт в тестах — администратор, он же включает платную версию.
"""
from datetime import date

from sqlalchemy import func, select

from app.models import Family, Household, HouseholdEvent, Intake, Medicine, Schedule, User
from app.plans import PLUS_HEADER
from tests.conftest import check_household_invariants, fid, grant_plus, register


# --- помощники ---
def billing_on(client, h):
    assert client.put("/api/admin/billing", headers=h, json={"enabled": True, "trial_days": 0}).status_code == 200


def code_of(client, h, f):
    return client.get(f"/api/families/{f}", headers=h).json()["invite_code"]


def me(client, h):
    return client.get("/api/auth/me", headers=h).json()


def cabinet_ids(client, h):
    return [f["id"] for f in me(client, h)["families"]]


def add_med(client, h, f, name="Нурофен"):
    r = client.post(f"/api/families/{f}/medicines", headers=h, json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def family(client, name="Никита", email="nikita@example.com"):
    """Семья с владельцем: (заголовки, пользователь, id аптечки)."""
    h, u = register(client, email, name)
    return h, u, fid(u)


def join_family(client, h_owner, f, name="Мама", email="mom@example.com"):
    """Новый человек регистрируется по приглашению владельца."""
    return register(client, email, name, invite=code_of(client, h_owner, f))


def counts(session_factory):
    with session_factory() as db:
        return {m.__name__: db.scalar(select(func.count()).select_from(m)) for m in (Household, Family, User)}


def delete_account(client, h, password="secret123"):
    return client.request("DELETE", "/api/auth/me", json={"password": password}, headers=h)


# --- R01. Один человек состоит ровно в одной семье ---
def test_r01_t1_register_without_code_creates_household_cabinet_owner(client, session_factory):
    h, u = register(client)
    assert [f["role"] for f in u["families"]] == ["owner"]
    with session_factory() as db:
        house = db.scalars(select(Household)).one()
        assert [(m.id, m.household_role) for m in house.members] == [(u["id"], "owner")]
        assert len(house.cabinets) == 1 and house.cabinets[0].created_by_id == u["id"]
    check_household_invariants(session_factory)


def test_r01_t2_register_with_code_joins_without_personal_household(client, session_factory):
    h, _, f = family(client)
    _, mom = join_family(client, h, f)
    assert [x["id"] for x in mom["families"]] == [f] and mom["families"][0]["role"] == "member"
    assert counts(session_factory) == {"Household": 1, "Family": 1, "User": 2}
    check_household_invariants(session_factory)


def test_r01_t3_joining_does_not_leave_a_person_in_two_households(client, session_factory):
    h, _, f = family(client)
    hm, mom = register(client, "mom@example.com", "Мама")
    assert counts(session_factory)["Household"] == 2
    assert client.post("/api/families/join", headers=hm, json={"code": code_of(client, h, f)}).status_code == 200
    assert counts(session_factory) == {"Household": 1, "Family": 1, "User": 2}
    assert cabinet_ids(client, hm) == [f]
    check_household_invariants(session_factory)


def test_r01_t4_after_leaving_a_person_gets_personal_household(client, session_factory):
    h, _, f = family(client)
    hm, mom = join_family(client, h, f)
    assert client.delete(f"/api/families/{f}/members/{mom['id']}", headers=hm).status_code == 204
    mine = me(client, hm)["families"]
    assert len(mine) == 1 and mine[0]["id"] != f and mine[0]["role"] == "owner"
    assert counts(session_factory)["Household"] == 2
    check_household_invariants(session_factory)


# --- R02. Лимит людей и роль владельца ---
def test_r02_t1_fourth_person_does_not_join_free_family(client, session_factory):
    h, _, f = family(client)
    billing_on(client, h)
    for i in range(2):
        join_family(client, h, f, f"Родной {i}", f"r{i}@example.com")
    r = client.post("/api/auth/register", json={
        "email": "late@example.com", "name": "Четвёртый", "password": "secret123",
        "invite_code": code_of(client, h, f), "consent": True,
    })
    assert r.status_code == 402 and r.headers[PLUS_HEADER] == "no_limits"
    hl, _ = register(client, "solo@example.com", "Одиночка")
    r = client.post("/api/families/join", headers=hl, json={"code": code_of(client, h, f)})
    assert r.status_code == 402 and r.headers[PLUS_HEADER] == "no_limits"
    check_household_invariants(session_factory)


def test_r02_t2_plus_fifth_person_joins_sixth_does_not(client, session_factory):
    h, _, f = family(client)
    billing_on(client, h)
    grant_plus(client, h, f)
    for i in range(4):
        join_family(client, h, f, f"Родной {i}", f"r{i}@example.com")
    r = client.post("/api/auth/register", json={
        "email": "late@example.com", "name": "Шестой", "password": "secret123",
        "invite_code": code_of(client, h, f), "consent": True,
    })
    assert r.status_code == 409
    assert len(client.get(f"/api/families/{f}", headers=h).json()["members"]) == 5
    check_household_invariants(session_factory)


def test_r02_t3_family_always_has_one_owner(client, session_factory):
    h, a, f = family(client)
    hb, b = join_family(client, h, f, "Боря", "b@example.com")
    hc, c = join_family(client, h, f, "Вера", "c@example.com")
    owners = lambda: [m["name"] for m in client.get(f"/api/families/{f}", headers=h).json()["members"] if m["role"] == "owner"]  # noqa: E731
    assert owners() == ["Никита"]
    assert client.patch(f"/api/families/{f}/members/{b['id']}", headers=h, json={"role": "owner"}).status_code == 200
    assert owners() == ["Боря"]  # прежний владелец стал участником
    check_household_invariants(session_factory)
    assert client.delete(f"/api/families/{f}/members/{c['id']}", headers=hb).status_code == 204  # владелец исключил
    assert owners() == ["Боря"]
    assert client.patch(f"/api/families/{f}/members/{a['id']}", headers=hb, json={"role": "owner"}).status_code == 200
    assert delete_account(client, hb).status_code == 204  # Боря уже участник и просто уходит
    assert owners() == ["Никита"]
    check_household_invariants(session_factory)


def test_r02_t4_members_list_has_owner_first_with_flag(client):
    h, _, f = family(client)
    hm, _ = join_family(client, h, f)
    members = client.get(f"/api/families/{f}", headers=hm).json()["members"]
    assert [(m["name"], m["is_owner"]) for m in members] == [("Никита", True), ("Мама", False)]


# --- R03. Лимит аптечек ---
def test_r03_t1_one_person_free_cannot_create_second_cabinet(client, session_factory):
    h, _, f = family(client)
    billing_on(client, h)
    r = client.post("/api/families", headers=h, json={"name": "Дача"})
    assert r.status_code == 402 and r.headers[PLUS_HEADER] == "cabinets"
    assert cabinet_ids(client, h) == [f]
    check_household_invariants(session_factory)


def test_r03_t2_two_people_free_have_two_cabinets_not_three(client, session_factory):
    h, _, f = family(client)
    billing_on(client, h)
    hm, _ = join_family(client, h, f)
    assert client.post("/api/families", headers=hm, json={"name": "Дача"}).status_code == 201  # создать может любой человек
    r = client.post("/api/families", headers=h, json={"name": "Гараж"})
    assert r.status_code == 402 and r.headers[PLUS_HEADER] == "cabinets"
    check_household_invariants(session_factory)


def test_r03_t3_plus_allows_eight_cabinets_not_nine(client, session_factory):
    h, _, f = family(client)
    billing_on(client, h)
    grant_plus(client, h, f)
    for i in range(7):
        assert client.post("/api/families", headers=h, json={"name": f"Аптечка {i}"}).status_code == 201
    assert client.post("/api/families", headers=h, json={"name": "Лишняя"}).status_code == 409
    assert len(cabinet_ids(client, h)) == 8
    check_household_invariants(session_factory)


def test_r03_t4_joining_with_an_empty_cabinet_dissolves_it(client, session_factory):
    h, _, f = family(client)
    hm, mom = register(client, "mom@example.com", "Мама")
    own = fid(mom)
    assert client.post("/api/families/join", headers=hm, json={"code": code_of(client, h, f)}).status_code == 200
    assert cabinet_ids(client, hm) == [f]
    assert client.get(f"/api/families/{own}", headers=hm).status_code == 404
    with session_factory() as db:
        assert db.get(Family, own) is None and len(db.get(Family, f).household.cabinets) == 1
    check_household_invariants(session_factory)


def test_r03_t5_last_cabinet_cannot_be_deleted(client, session_factory):
    h, _, f = family(client)
    r = client.delete(f"/api/families/{f}", headers=h)
    assert r.status_code == 409 and "последняя" in r.json()["detail"]
    assert cabinet_ids(client, h) == [f]
    check_household_invariants(session_factory)


# --- R05. Тариф один на всю семью ---
def test_r05_t1_t2_plan_is_shared_by_all_members(client, session_factory):
    h, _, f = family(client)
    billing_on(client, h)
    hm, mom = join_family(client, h, f)
    has_plus = lambda hh: client.get(f"/api/families/{f}/plan", headers=hh).json()["has_plus"]  # noqa: E731
    assert (has_plus(h), has_plus(hm)) == (False, False)  # R05-T2
    grant_plus(client, h, f)
    assert (has_plus(h), has_plus(hm)) == (True, True)  # R05-T1
    assert client.get("/api/payments/me", headers=hm).json()["plus_active"] is True
    check_household_invariants(session_factory)


# --- R08. Вступление в другую семью (без выбора по Плюсу, он в следующем шаге) ---
def test_r08_t1_free_person_brings_cabinet_with_medicines(client, session_factory):
    h, _, f = family(client)
    hm, mom = register(client, "mom@example.com", "Мама")
    own = fid(mom)
    add_med(client, hm, own, "Но-шпа")
    assert client.post("/api/families/join", headers=hm, json={"code": code_of(client, h, f)}).status_code == 200
    assert sorted(cabinet_ids(client, hm)) == sorted([f, own]) and sorted(cabinet_ids(client, h)) == sorted([f, own])
    assert [m["name"] for m in client.get(f"/api/families/{own}/medicines", headers=h).json()] == ["Но-шпа"]
    assert counts(session_factory)["Household"] == 1
    check_household_invariants(session_factory)


def test_r08_t3_bringing_too_many_cabinets_is_refused_without_changes(client, session_factory):
    h, _, f = family(client)
    for name in ("Дача", "Гараж"):  # пока платная версия выключена, лишние аптечки создаются свободно
        client.post("/api/families", headers=h, json={"name": name})
    billing_on(client, h)
    hm, mom = register(client, "mom@example.com", "Мама")
    own = fid(mom)
    add_med(client, hm, own)
    r = client.post("/api/families/join", headers=hm, json={"code": code_of(client, h, f)})
    assert r.status_code == 402 and r.headers[PLUS_HEADER] == "cabinets"
    assert cabinet_ids(client, hm) == [own]  # ничего не изменилось
    assert counts(session_factory)["Household"] == 2


def test_r08_t8_paid_plus_person_cannot_join_and_lose_paid_days(client, session_factory):
    h, _, f = family(client)
    hm, mom = register(client, "mom@example.com", "Мама")
    grant_plus(client, h, fid(mom), until="2030-01-01T00:00:00Z")
    r = client.post("/api/families/join", headers=hm, json={"code": code_of(client, h, f)})
    assert r.status_code == 409 and "оплачен Плюс" in r.json()["detail"]
    assert cabinet_ids(client, hm) == [fid(mom)]
    check_household_invariants(session_factory)


def test_r08_t9_owner_of_a_multi_person_family_cannot_join(client, session_factory):
    h, _, f = family(client)
    join_family(client, h, f)
    hb, b = register(client, "b@example.com", "Боря")
    hv, v = register(client, "v@example.com", "Вера")
    assert client.post("/api/families/join", headers=h, json={"code": code_of(client, hb, fid(b))}).status_code == 409
    check_household_invariants(session_factory)


# --- R09/R10. Выход и исключение ---
def two_cabinets_of_mom(client):
    h, _, f = family(client)
    hm, mom = join_family(client, h, f)
    first = client.post("/api/families", headers=hm, json={"name": "Дача"}).json()["id"]
    second = client.post("/api/families", headers=hm, json={"name": "Гараж"}).json()["id"]
    return (h, f), (hm, mom), (first, second)


def test_r09_t1_leaving_takes_the_oldest_cabinet_created_by_self(client, session_factory):
    (h, f), (hm, mom), (first, second) = two_cabinets_of_mom(client)
    add_med(client, hm, first, "Из дачи")
    assert client.delete(f"/api/families/{f}/members/{mom['id']}", headers=hm).status_code == 204
    assert cabinet_ids(client, hm) == [first]  # дача уехала с ней, гараж остался семье
    assert sorted(cabinet_ids(client, h)) == sorted([f, second])
    assert client.get(f"/api/families/{first}", headers=h).status_code == 404
    check_household_invariants(session_factory)


def test_bc22_leaving_with_two_cabinets_takes_one(client, session_factory):
    (h, f), (hm, mom), (first, second) = two_cabinets_of_mom(client)
    assert client.delete(f"/api/families/{f}/members/{mom['id']}", headers=hm).status_code == 204
    assert len(cabinet_ids(client, hm)) == 1 and len(cabinet_ids(client, h)) == 2
    check_household_invariants(session_factory)


def test_r09_t2_member_without_own_cabinets_gets_an_empty_one(client, session_factory):
    h, _, f = family(client)
    hm, mom = join_family(client, h, f)
    assert client.delete(f"/api/families/{f}/members/{mom['id']}", headers=hm).status_code == 204
    own = cabinet_ids(client, hm)
    assert len(own) == 1 and own[0] != f
    assert client.get(f"/api/families/{own[0]}/medicines", headers=hm).json() == []
    assert cabinet_ids(client, h) == [f]
    check_household_invariants(session_factory)


def test_r09_t3_personal_data_goes_with_the_person(client, session_factory):
    h, a, f = family(client)
    hm, mom = join_family(client, h, f)
    med = add_med(client, h, f, "Общее")
    with session_factory() as db:
        db.add(Intake(family_id=f, medicine_id=med, medicine_name="Общее", user_id=mom["id"], amount=1))
        db.add(Intake(family_id=f, medicine_id=med, medicine_name="Общее", user_id=a["id"], amount=2))
        db.add(Schedule(family_id=f, user_id=mom["id"], medicine_id=med, medicine_name="Общее", start_date=date(2026, 10, 1)))
        db.commit()
    assert client.delete(f"/api/families/{f}/members/{mom['id']}", headers=hm).status_code == 204
    (new,) = cabinet_ids(client, hm)
    with session_factory() as db:
        mine = db.scalars(select(Intake).where(Intake.user_id == mom["id"])).all()
        assert [(i.family_id, i.medicine_id, i.medicine_name) for i in mine] == [(new, None, "Общее")]  # название осталось
        assert db.scalars(select(Intake).where(Intake.user_id == a["id"])).one().family_id == f  # у семьи осталась история только её людей
        assert db.scalar(select(func.count()).select_from(Schedule)) == 0  # лекарства остались в старой аптечке
    check_household_invariants(session_factory)


def test_r09_t5_person_living_alone_cannot_leave(client, session_factory):
    h, u, f = family(client)
    r = client.delete(f"/api/families/{f}/members/{u['id']}", headers=h)
    assert r.status_code == 409 and "живёте один" in r.json()["detail"]
    assert cabinet_ids(client, h) == [f]
    check_household_invariants(session_factory)


def test_r10_owner_kicks_member_but_cannot_be_kicked(client, session_factory):
    h, a, f = family(client)
    hm, mom = join_family(client, h, f)
    hb, b = join_family(client, h, f, "Боря", "b@example.com")
    assert client.delete(f"/api/families/{f}/members/{a['id']}", headers=hm).status_code == 403  # участник чужих не исключает
    assert client.delete(f"/api/families/{f}/members/{mom['id']}", headers=h).status_code == 204
    assert len(cabinet_ids(client, hm)) == 1 and cabinet_ids(client, hm) != [f]
    r = client.delete(f"/api/families/{f}/members/{a['id']}", headers=h)  # владелец не исключает сам себя
    assert r.status_code == 409 and "передаёт владение" in r.json()["detail"]
    with session_factory() as db:
        kinds = [e.kind for e in db.scalars(select(HouseholdEvent).order_by(HouseholdEvent.id))]
    assert "kick" in kinds
    check_household_invariants(session_factory)


# --- R16. Ручная выдача Плюса семье ---
def test_r16_t1_admin_grants_plus_to_the_family_and_it_is_logged(client, session_factory):
    h, a, f = family(client)
    billing_on(client, h)
    hm, mom = join_family(client, h, f)
    assert client.get(f"/api/families/{f}/plan", headers=hm).json()["plus_active"] is False
    grant_plus(client, h, f, until="2030-01-01T00:00:00Z")
    plan = client.get(f"/api/families/{f}/plan", headers=hm).json()
    assert plan["plus_active"] is True and plan["plus_until"].startswith("2030-01-01")
    fam = next(x for x in client.get("/api/admin/families", headers=h).json() if x["id"] == f)
    events = client.get(f"/api/admin/households/{fam['household_id']}/events", headers=h).json()
    assert [(e["kind"], e["actor_id"], e["user_id"]) for e in events if e["kind"] == "plan"] == [("plan", a["id"], a["id"])]
    assert "2030-01-01" in events[0]["detail"]
    check_household_invariants(session_factory)


def test_r16_t2_removing_plus_clears_autorenew_of_the_whole_family(client, session_factory):
    h, a, f = family(client)
    hm, mom = join_family(client, h, f)
    grant_plus(client, h, f)
    with session_factory() as db:
        for uid in (a["id"], mom["id"]):
            u = db.get(User, uid)
            u.auto_renew, u.pay_method_id, u.renew_period = True, "pm-1", "month"
        db.commit()
    grant_plus(client, h, f, plan="free")
    with session_factory() as db:
        assert [(u.auto_renew, u.pay_method_id) for u in db.scalars(select(User))] == [(False, None), (False, None)]
        assert db.scalars(select(Household)).one().plan == "free"


def test_r16_t3_admin_sees_owner_people_cabinets_and_end_date(client):
    h, _, f = family(client)
    join_family(client, h, f)
    client.post("/api/families", headers=h, json={"name": "Дача"})
    grant_plus(client, h, f, until="2030-01-01T00:00:00Z")
    fam = next(x for x in client.get("/api/admin/families", headers=h).json() if x["id"] == f)
    assert (fam["owner_name"], fam["household_people"], fam["household_cabinets"]) == ("Никита", 2, 2)
    assert fam["plus_until"].startswith("2030-01-01") and fam["plus_active"] is True


def test_r16_t4_regular_user_cannot_touch_plans_or_events(client):
    h, u, f = family(client)
    hm, mom = join_family(client, h, f)
    assert client.put(f"/api/admin/users/{u['id']}/plan", headers=hm, json={"plan": "plus"}).status_code == 403
    assert client.get("/api/admin/households/1/events", headers=hm).status_code == 403


# --- R22. Удаление аккаунта ---
def test_r22_t1_member_deletion_keeps_family_and_his_cabinets(client, session_factory):
    h, a, f = family(client)
    hm, mom = join_family(client, h, f)
    dacha = client.post("/api/families", headers=hm, json={"name": "Дача"}).json()["id"]
    add_med(client, hm, dacha, "Дачное")
    assert delete_account(client, hm).status_code == 204
    assert sorted(cabinet_ids(client, h)) == sorted([f, dacha])  # аптечки остались семье
    assert [m["name"] for m in client.get(f"/api/families/{dacha}/medicines", headers=h).json()] == ["Дачное"]
    assert [m["name"] for m in client.get(f"/api/families/{f}", headers=h).json()["members"]] == ["Никита"]
    check_household_invariants(session_factory)


def test_r22_t2_last_member_deletion_removes_family_and_cabinets(client, session_factory):
    h, u, f = family(client)
    client.post("/api/families", headers=h, json={"name": "Дача"})
    add_med(client, h, f)
    assert delete_account(client, h).status_code == 204
    assert counts(session_factory) == {"Household": 0, "Family": 0, "User": 0}
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Medicine)) == 0
    check_household_invariants(session_factory)


def test_r22_t3_owner_with_other_people_must_transfer_ownership_first(client, session_factory):
    h, a, f = family(client)
    hm, mom = join_family(client, h, f)
    r = delete_account(client, h)
    assert r.status_code == 409 and "передайте владение" in r.json()["detail"]
    assert client.get("/api/auth/me", headers=h).status_code == 200  # аккаунт на месте
    check_household_invariants(session_factory)


# --- R24. Удаление аптечки ---
def test_r24_t1_creator_deletes_own_cabinet_with_its_data(client, session_factory):
    h, _, f = family(client)
    hm, mom = join_family(client, h, f)
    dacha = client.post("/api/families", headers=hm, json={"name": "Дача"}).json()["id"]
    med = add_med(client, hm, dacha)
    client.post(f"/api/families/{dacha}/medicines/{med}/packages", headers=hm, json={"quantity": 2})
    with session_factory() as db:
        db.add(Schedule(family_id=dacha, user_id=mom["id"], medicine_id=med, medicine_name="Нурофен", start_date=date(2026, 10, 1)))
        db.commit()
    assert client.delete(f"/api/families/{dacha}", headers=hm).status_code == 204
    assert client.get(f"/api/families/{dacha}", headers=hm).status_code == 404
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Medicine)) == 0
        assert db.scalar(select(func.count()).select_from(Schedule)) == 0
    check_household_invariants(session_factory)


def test_r24_t2_owner_deletes_someone_elses_cabinet(client, session_factory):
    h, _, f = family(client)
    hm, _ = join_family(client, h, f)
    dacha = client.post("/api/families", headers=hm, json={"name": "Дача"}).json()["id"]
    assert client.delete(f"/api/families/{dacha}", headers=h).status_code == 204
    assert cabinet_ids(client, h) == [f]
    check_household_invariants(session_factory)


def test_r24_t3_other_member_cannot_delete_foreign_cabinet(client, session_factory):
    h, _, f = family(client)
    hm, _ = join_family(client, h, f)
    hb, _ = join_family(client, h, f, "Боря", "b@example.com")
    dacha = client.post("/api/families", headers=hm, json={"name": "Дача"}).json()["id"]
    assert client.delete(f"/api/families/{dacha}", headers=hb).status_code == 403
    assert dacha in cabinet_ids(client, hm)
    check_household_invariants(session_factory)


def test_r24_t4_last_cabinet_is_protected_even_for_owner(client, session_factory):
    h, _, f = family(client)
    hm, _ = join_family(client, h, f)
    assert client.delete(f"/api/families/{f}", headers=h).status_code == 409
    check_household_invariants(session_factory)


def test_r24_t5_delete_then_create_does_not_exceed_the_limit(client, session_factory):
    h, _, f = family(client)
    billing_on(client, h)
    hm, _ = join_family(client, h, f)
    second = client.post("/api/families", headers=hm, json={"name": "Дача"}).json()["id"]
    assert client.delete(f"/api/families/{second}", headers=hm).status_code == 204
    assert client.post("/api/families", headers=hm, json={"name": "Гараж"}).status_code == 201
    assert client.post("/api/families", headers=hm, json={"name": "Ещё"}).status_code == 402
    assert len(cabinet_ids(client, h)) == 2
    check_household_invariants(session_factory)


# --- R26. Лимит лекарств считается по каждой аптечке ---
def test_r26_t3_medicine_limit_is_per_cabinet(client, session_factory):
    h, _, f = family(client)
    billing_on(client, h)
    hm, _ = join_family(client, h, f)
    second = client.post("/api/families", headers=hm, json={"name": "Дача"}).json()["id"]
    with session_factory() as db:
        db.add_all(Medicine(family_id=f, name=f"Лекарство {i}") for i in range(60))
        db.commit()
    assert client.post(f"/api/families/{f}/medicines", headers=h, json={"name": "61-е"}).status_code == 402
    assert client.post(f"/api/families/{second}/medicines", headers=h, json={"name": "В другую"}).status_code == 201
    check_household_invariants(session_factory)


# --- Бизнес-кейсы ---
def test_bc01_one_person(client, session_factory):
    h, u, f = family(client)
    billing_on(client, h)
    for name in ("Нурофен", "Аспирин"):
        add_med(client, h, f, name)
    assert client.post("/api/families", headers=h, json={"name": "Дача"}).status_code == 402
    grant_plus(client, h, f)  # покупка Плюса
    for i in range(7):
        assert client.post("/api/families", headers=h, json={"name": f"Аптечка {i}"}).status_code == 201
    assert len(cabinet_ids(client, h)) == 8
    check_household_invariants(session_factory)


def test_bc02_registration_by_invitation(client, session_factory):
    h, a, f = family(client)
    hm, mom = join_family(client, h, f)
    assert counts(session_factory) == {"Household": 1, "Family": 1, "User": 2}
    with session_factory() as db:
        house = db.scalars(select(Household)).one()
        assert (house.plan, house.plus_is_trial) == ("free", False)  # приглашённый пробного не приносит
        assert db.get(User, mom["id"]).household_role == "member"
    check_household_invariants(session_factory)


def test_bc03_free_family_grows_to_three_people_and_three_cabinets(client, session_factory):
    h, _, f = family(client)
    billing_on(client, h)
    hb, _ = join_family(client, h, f, "Боря", "b@example.com")
    hc, _ = join_family(client, h, f, "Вера", "c@example.com")
    assert len(client.get(f"/api/families/{f}", headers=h).json()["members"]) == 3
    for name in ("Дача", "Гараж"):
        assert client.post("/api/families", headers=h, json={"name": name}).status_code == 201
    assert client.post("/api/families", headers=h, json={"name": "Лишняя"}).status_code == 402
    r = client.post("/api/auth/register", json={
        "email": "d@example.com", "name": "Четвёртый", "password": "secret123",
        "invite_code": code_of(client, h, f), "consent": True,
    })
    assert r.status_code == 402
    check_household_invariants(session_factory)

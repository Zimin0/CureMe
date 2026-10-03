"""Одновременные запросы (R20): проверка и запись идут под блокировкой строки семьи. Нужен Postgres: у SQLite нет блокировок строк."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import HouseholdInvite, User, utcnow
from tests.conftest import check_household_invariants, fid, grant_plus, invite_of, register

pytestmark = pytest.mark.skipif(not os.environ.get("CUREME_TEST_DATABASE_URL"), reason="блокировки строк проверяются на Postgres")


def race(calls):
    """Запускает запросы одновременно (каждый в своём потоке и со своим клиентом) и возвращает коды ответов."""
    barrier = Barrier(len(calls))

    def run(call):
        barrier.wait()
        with TestClient(app) as c:
            return call(c).status_code

    with ThreadPoolExecutor(len(calls)) as pool:
        return sorted(pool.map(run, calls))


def billing_on(client, h):
    assert client.put("/api/admin/billing", headers=h, json={"enabled": True, "trial_days": 0}).status_code == 200


def test_r20_t1_bc23_two_joins_for_one_free_seat_let_one_through(client, session_factory):
    h, u = register(client)
    f = fid(u)
    billing_on(client, h)
    register(client, "mom@example.com", "Мама", invite=invite_of(client, h, f))  # в семье двое, свободно одно место из трёх
    code_a = invite_of(client, h, f)
    with session_factory() as db:  # второй действующий код кладём в базу: через API у владельца он всегда один (R04)
        house = db.get(User, u["id"]).household
        db.add(HouseholdInvite(household_id=house.id, code="SECOND22", expires_at=utcnow() + timedelta(hours=24)))
        db.commit()
    ha, _ = register(client, "a@example.com", "Аня")
    hb, _ = register(client, "b@example.com", "Боря")
    join = lambda hh, code: (lambda c: c.post("/api/families/join", headers=hh, json={"code": code}))  # noqa: E731
    assert race([join(ha, code_a), join(hb, "SECOND22")]) == [200, 402]
    assert len(client.get(f"/api/families/{f}", headers=h).json()["members"]) == 3
    check_household_invariants(session_factory)


def test_r04_t7_two_joins_with_one_code_let_one_through(client, session_factory):
    """Одноразовый код при одновременных запросах: сработает один, второй получит 404 (R04, R20)."""
    h, u = register(client)
    f = fid(u)
    code = invite_of(client, h, f)
    ha, _ = register(client, "a@example.com", "Аня")
    hb, _ = register(client, "b@example.com", "Боря")
    join = lambda hh: (lambda c: c.post("/api/families/join", headers=hh, json={"code": code}))  # noqa: E731
    assert race([join(ha), join(hb)]) == [200, 404]
    assert len(client.get(f"/api/families/{f}", headers=h).json()["members"]) == 2
    check_household_invariants(session_factory)


def test_r04_t7_two_registrations_with_one_code_let_one_through(client, session_factory):
    h, u = register(client)
    f = fid(u)
    code = invite_of(client, h, f)
    signup = lambda email: (lambda c: c.post("/api/auth/register", json={  # noqa: E731
        "email": email, "name": "Новый", "password": "secret123", "invite_code": code, "consent": True}))
    assert race([signup("a@example.com"), signup("b@example.com")]) == [201, 400]
    assert len(client.get(f"/api/families/{f}", headers=h).json()["members"]) == 2
    check_household_invariants(session_factory)


def test_r20_t2_two_cabinet_creations_for_one_slot_let_one_through(client, session_factory):
    h, u = register(client)
    f = fid(u)
    billing_on(client, h)
    code = client.get(f"/api/families/{f}", headers=h).json()["invite_code"]
    hm, _ = register(client, "mom@example.com", "Мама", invite=code)  # людей двое: слот под вторую аптечку один
    create = lambda hh, name: (lambda c: c.post("/api/families", headers=hh, json={"name": name}))  # noqa: E731
    assert race([create(h, "Дача"), create(hm, "Гараж")]) == [201, 402]
    assert len(client.get("/api/auth/me", headers=h).json()["families"]) == 2
    check_household_invariants(session_factory)


def test_r20_crossed_joins_do_not_deadlock(client, session_factory):
    """Два одиночки одновременно вступают друг к другу: блокировки берутся в одном порядке, один вступает, второй получает отказ."""
    register(client)  # администратор
    ha, a = register(client, "a@example.com", "Аня")
    hb, b = register(client, "b@example.com", "Боря")
    code = lambda hh, u: client.get(f"/api/families/{fid(u)}", headers=hh).json()["invite_code"]  # noqa: E731
    ca, cb = code(ha, a), code(hb, b)
    codes = sorted(race([
        lambda c: c.post("/api/families/join", headers=ha, json={"code": cb}),
        lambda c: c.post("/api/families/join", headers=hb, json={"code": ca}),
    ]))
    assert codes[0] == 200 and codes[1] in (200, 404, 409)  # главное: не 500 от взаимной блокировки
    check_household_invariants(session_factory)


def three_people(client):
    h, u = register(client)
    f = fid(u)
    hm, mom = register(client, "mom@example.com", "Мама", invite=invite_of(client, h, f))
    hd, dad = register(client, "dad@example.com", "Папа", invite=invite_of(client, h, f))
    return f, h, hm, mom, hd, dad


def owners(client, h, f):
    return [m["name"] for m in client.get(f"/api/families/{f}", headers=h).json()["members"] if m["role"] == "owner"]


def test_r23_t11_two_offers_at_once_leave_one_pending(client, session_factory):
    """Владелец нажал «Передать» дважды для разных людей: создаётся одно предложение, второе получает 409 (R23, R20)."""
    f, h, hm, mom, hd, dad = three_people(client)
    offer = lambda uid: (lambda c: c.post(f"/api/families/{f}/owner-transfer", headers=h, json={"user_id": uid}))  # noqa: E731
    assert race([offer(mom["id"]), offer(dad["id"])]) == [201, 409]
    assert owners(client, h, f) == ["Никита"]
    check_household_invariants(session_factory)


def test_r23_t11_double_accept_transfers_once(client, session_factory):
    from sqlalchemy import select

    from app.models import HouseholdEvent

    f, h, hm, mom, hd, dad = three_people(client)
    assert client.post(f"/api/families/{f}/owner-transfer", headers=h, json={"user_id": mom["id"]}).status_code == 201
    accept = lambda c: c.post(f"/api/families/{f}/owner-transfer/accept", headers=hm)  # noqa: E731
    assert race([accept, accept]) == [200, 404]
    assert owners(client, h, f) == ["Мама"]
    with session_factory() as db:
        assert len(db.scalars(select(HouseholdEvent).where(HouseholdEvent.kind == "owner")).all()) == 1
    check_household_invariants(session_factory)


def test_r23_t11_accept_and_withdraw_at_once_give_one_outcome(client, session_factory):
    """Принять и забрать одновременно: выигрывает один, владелец остаётся согласованным (R23, R20)."""
    f, h, hm, mom, hd, dad = three_people(client)
    assert client.post(f"/api/families/{f}/owner-transfer", headers=h, json={"user_id": mom["id"]}).status_code == 201
    accept = lambda c: c.post(f"/api/families/{f}/owner-transfer/accept", headers=hm)  # noqa: E731
    withdraw = lambda c: c.delete(f"/api/families/{f}/owner-transfer", headers=h)  # noqa: E731
    codes = race([accept, withdraw])
    assert codes == [200, 404] or codes == [200, 200], codes  # забрать до принятия: принять уже нельзя; иначе принято
    assert owners(client, h, f) in (["Мама"], ["Никита"])
    check_household_invariants(session_factory)

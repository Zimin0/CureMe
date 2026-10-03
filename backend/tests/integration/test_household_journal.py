"""Журнал семьи (R27): без имён в записях, хранится 12 месяцев, удаляется вместе с семьёй, при удалении аккаунта обезличивается."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app import households
from app.models import Household, HouseholdEvent, User
from tests.conftest import check_household_invariants, fid, hand_over, invite_of, register


def events(session_factory):
    with session_factory() as db:
        return list(db.scalars(select(HouseholdEvent).order_by(HouseholdEvent.id)))


def delete_account(client, h):
    return client.request("DELETE", "/api/auth/me", json={"password": "secret123"}, headers=h)


def test_r27_t1_no_names_in_journal_details(client, owner, session_factory):
    h, u, f = owner
    hm, mom = register(client, "mom@example.com", "Мама", invite=invite_of(client, h, f))
    hand_over(client, h, f, mom["id"], hm)  # смена владельца
    r = client.post("/api/families", headers=hm, json={"name": "Дача Мамы"})  # своя аптечка с именем в названии
    assert r.status_code == 201
    client.delete(f"/api/families/{r.json()['id']}", headers=hm)
    kinds = [e.kind for e in events(session_factory)]
    assert {"owner", "cabinet_add", "cabinet_delete", "join"} <= set(kinds)
    text = " ".join(e.detail for e in events(session_factory))
    for name in ("Никита", "Мама", "Дача", "nikita", "mom@"):
        assert name not in text
    owner_event = next(e for e in events(session_factory) if e.kind == "owner")
    assert owner_event.detail == f"прежний владелец: {u['id']}"  # только номер


def test_r27_t2_journal_goes_with_the_family(client, owner, session_factory):
    """Семья из одного человека удаляется вместе с аккаунтом: записи журнала не остаются ни с номером семьи, ни без него."""
    h, u, f = owner
    client.post("/api/families", headers=h, json={"name": "Вторая"})  # в журнале есть записи этой семьи
    assert events(session_factory)
    assert delete_account(client, h).status_code == 204
    assert events(session_factory) == []  # и сирот с household_id = NULL нет
    with session_factory() as db:
        assert db.scalars(select(Household)).all() == []


def test_r27_t2_joining_dissolves_the_empty_personal_family_with_its_journal(client, owner, session_factory):
    h, u, f = owner
    hs, stranger = register(client, "solo@example.com", "Один")  # личная семья, пустая аптечка
    with session_factory() as db:
        solo_house = db.get(User, stranger["id"]).household_id
        households.record(db, db.get(Household, solo_house), "cabinet_add", detail="аптечка №99")
        db.commit()
    assert client.post("/api/families/join", headers=hs, json={"code": invite_of(client, h, f)}).status_code == 200
    with session_factory() as db:
        assert db.get(Household, solo_house) is None
        assert db.scalars(select(HouseholdEvent).where(HouseholdEvent.household_id.is_(None))).all() == []
    check_household_invariants(session_factory)


def test_r27_t3_deleting_an_account_clears_the_person_in_the_journal(client, owner, session_factory):
    h, u, f = owner
    hm, mom = register(client, "mom@example.com", "Мама", invite=invite_of(client, h, f))
    hd, dad = register(client, "dad@example.com", "Папа", invite=invite_of(client, h, f))
    client.delete(f"/api/families/{f}/members/{dad['id']}", headers=h)  # исключён владельцем: в записи Папа и Никита
    assert delete_account(client, hm).status_code == 204  # Мама удалила аккаунт
    ids = {e.user_id for e in events(session_factory)} | {e.actor_id for e in events(session_factory)}
    assert mom["id"] not in ids  # её номера в журнале больше нет
    assert u["id"] in ids and dad["id"] in ids  # остальные записи на месте
    assert any(e.kind == "join" and e.user_id is None for e in events(session_factory))  # запись о вступлении осталась, без человека


def test_r27_t4_events_older_than_12_months_are_deleted(client, owner, session_factory):
    h, u, f = owner
    client.post("/api/families", headers=h, json={"name": "Дача"})
    with session_factory() as db:
        old = db.scalars(select(HouseholdEvent)).first()
        old.created_at = datetime.now(timezone.utc) - timedelta(days=366)
        db.commit()
        left = len(db.scalars(select(HouseholdEvent)).all()) - 1
        assert households.purge_old_events(db) == 1
        assert len(db.scalars(select(HouseholdEvent)).all()) == left  # свежие остались
        assert households.purge_old_events(db) == 0

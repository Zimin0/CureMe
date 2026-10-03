"""Передача владения семьёй (R23): только с согласием принимающего, предложение живёт 24 часа, кулдаун 7 дней."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app import households, mailer
from app.config import get_settings
from app.models import Household, HouseholdEvent, OwnerTransfer, User, utcnow
from tests.conftest import age_owner_events, check_household_invariants, hand_over, invite_of, register


def trio(client, owner):
    """Семья из троих: владелец Никита, участники Мама и Папа. Возвращает заголовки и id всех."""
    h, u, f = owner
    hm, mom = register(client, "mom@example.com", "Мама", invite=invite_of(client, h, f))
    hd, dad = register(client, "dad@example.com", "Папа", invite=invite_of(client, h, f))
    return f, (h, u), (hm, mom), (hd, dad)


def view(client, h, f):
    return client.get(f"/api/families/{f}", headers=h).json()


def owner_name(client, h, f):
    return next(m["name"] for m in view(client, h, f)["members"] if m["role"] == "owner")


def offer(client, h, f, user_id):
    return client.post(f"/api/families/{f}/owner-transfer", headers=h, json={"user_id": user_id})


def accept(client, h, f):
    return client.post(f"/api/families/{f}/owner-transfer/accept", headers=h)


def decline(client, h, f):
    return client.post(f"/api/families/{f}/owner-transfer/decline", headers=h)


def withdraw(client, h, f):
    return client.delete(f"/api/families/{f}/owner-transfer", headers=h)


def test_r23_t1_offer_and_acceptance_change_the_owner(client, owner, session_factory):
    f, (h, u), (hm, mom), (hd, _) = trio(client, owner)
    r = offer(client, h, f, mom["id"])
    assert r.status_code == 201
    t = r.json()["owner_transfer"]
    assert (t["kind"], t["from_name"], t["to_name"], t["can_withdraw"], t["can_answer"]) == ("offer", "Никита", "Мама", True, False)
    # пока Мама не ответила, владелец прежний; ей предложение видно с кнопкой «принять», третьему человеку нет
    assert owner_name(client, h, f) == "Никита"
    mine = view(client, hm, f)["owner_transfer"]
    assert (mine["can_answer"], mine["can_withdraw"]) == (True, False)
    assert client.get("/api/auth/me", headers=hm).json()["owner_transfer_waiting"] is True
    assert client.get("/api/auth/me", headers=h).json()["owner_transfer_waiting"] is False
    third = view(client, hd, f)["owner_transfer"]
    assert (third["can_answer"], third["can_withdraw"]) == (False, False)

    r = accept(client, hm, f)
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "owner" and body["owner_transfer"] is None
    roles = {m["name"]: m["role"] for m in body["members"]}
    assert roles == {"Мама": "owner", "Никита": "member", "Папа": "member"}  # прежний владелец стал участником
    assert client.get("/api/auth/me", headers=hm).json()["owner_transfer_waiting"] is False
    with session_factory() as db:
        kinds = [e.kind for e in db.scalars(select(HouseholdEvent).order_by(HouseholdEvent.id)) if e.kind.startswith("owner")]
        assert kinds == ["owner_offer", "owner"]  # предложение и сама передача записаны в журнал
        assert db.scalars(select(OwnerTransfer)).one().status == "accepted"
    check_household_invariants(session_factory)


def test_r23_t2_offer_without_answer_expires_in_24_hours(client, owner, session_factory):
    f, (h, u), (hm, mom), _ = trio(client, owner)
    assert offer(client, h, f, mom["id"]).status_code == 201
    with session_factory() as db:
        t = db.scalars(select(OwnerTransfer)).one()
        assert timedelta(hours=23, minutes=55) < households._aware(t.expires_at) - utcnow() <= timedelta(hours=24)
        t.expires_at = utcnow() - timedelta(minutes=1)  # прошло больше суток
        db.commit()
    assert view(client, h, f)["owner_transfer"] is None  # просроченное не показываем
    assert accept(client, hm, f).status_code == 404  # и принять уже нельзя
    assert owner_name(client, h, f) == "Никита"

    with session_factory() as db:  # фоновая задача закрывает запись и пишет в журнал
        assert households.expire_owner_transfers(db) == 1
        assert households.expire_owner_transfers(db) == 0
        assert db.scalars(select(OwnerTransfer)).one().status == "expired"
        assert [e.kind for e in db.scalars(select(HouseholdEvent)) if e.kind == "owner_expired"] == ["owner_expired"]
    assert offer(client, h, f, mom["id"]).status_code == 201  # смены владельца не было: можно предложить снова
    check_household_invariants(session_factory)


def test_r23_t2_expiry_is_also_applied_lazily(client, owner, session_factory):
    """Фоновая задача ещё не пробегала: просроченное предложение не мешает предложить новое."""
    f, (h, _), (hm, mom), (hd, dad) = trio(client, owner)
    assert offer(client, h, f, mom["id"]).status_code == 201
    with session_factory() as db:
        db.scalars(select(OwnerTransfer)).one().expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    assert offer(client, h, f, dad["id"]).status_code == 201
    assert view(client, hd, f)["owner_transfer"]["can_answer"] is True
    with session_factory() as db:
        assert sorted(t.status for t in db.scalars(select(OwnerTransfer))) == ["expired", "pending"]
    check_household_invariants(session_factory)


def test_r23_t3_member_asks_to_pay_and_owner_confirms(client, owner, session_factory):
    f, (h, _), (hm, mom), _ = trio(client, owner)
    r = client.post(f"/api/families/{f}/owner-request", headers=hm)
    assert r.status_code == 201
    t = r.json()["owner_transfer"]
    assert (t["kind"], t["from_name"], t["to_name"], t["can_withdraw"], t["can_answer"]) == ("request", "Мама", "Никита", True, False)
    seen_by_owner = view(client, h, f)["owner_transfer"]
    assert (seen_by_owner["can_answer"], seen_by_owner["can_withdraw"]) == (True, False)
    assert client.get("/api/auth/me", headers=h).json()["owner_transfer_waiting"] is True
    assert accept(client, hm, f).status_code == 404  # подтверждать должен владелец, а не тот, кто просит
    assert owner_name(client, h, f) == "Никита"

    r = accept(client, h, f)
    assert r.status_code == 200 and r.json()["role"] == "member"
    assert owner_name(client, h, f) == "Мама"
    check_household_invariants(session_factory)


def test_r23_t3_owner_can_decline_the_request(client, owner, session_factory):
    f, (h, _), (hm, _), _ = trio(client, owner)
    client.post(f"/api/families/{f}/owner-request", headers=hm)
    r = decline(client, h, f)
    assert r.status_code == 200 and r.json()["owner_transfer"] is None
    assert owner_name(client, h, f) == "Никита"
    with session_factory() as db:
        assert db.scalars(select(OwnerTransfer)).one().status == "declined"
    assert client.post(f"/api/families/{f}/owner-request", headers=hm).status_code == 201  # можно попросить снова


def test_r23_t4_nobody_becomes_owner_without_consent(client, owner, session_factory):
    f, (h, u), (hm, mom), (hd, dad) = trio(client, owner)
    # прежний способ (сразу назначить роль) исчез
    assert client.patch(f"/api/families/{f}/members/{mom['id']}", headers=h, json={"role": "owner"}).status_code in (404, 405)
    assert accept(client, hm, f).status_code == 404  # принимать нечего
    assert offer(client, h, f, mom["id"]).status_code == 201
    assert accept(client, hd, f).status_code == 404  # чужое предложение принять нельзя
    assert accept(client, h, f).status_code == 404  # и тому, кто предложил, тоже
    assert owner_name(client, h, f) == "Никита"
    r = decline(client, hm, f)  # Мама отказалась
    assert r.status_code == 200 and owner_name(client, h, f) == "Никита"
    assert accept(client, hm, f).status_code == 404  # отказ окончательный, принять после него нельзя
    with session_factory() as db:
        assert [u.household_role for u in db.scalars(select(User).order_by(User.id))] == ["owner", "member", "member"]
    check_household_invariants(session_factory)


def test_r23_t5_second_transfer_within_7_days_is_refused(client, owner, session_factory):
    f, (h, u), (hm, mom), (hd, dad) = trio(client, owner)
    hand_over(client, h, f, mom["id"], hm)
    again = view(client, hm, f)["next_transfer_at"]
    assert again and timedelta(days=6, hours=23) < datetime.fromisoformat(again).astimezone(timezone.utc) - datetime.now(timezone.utc) <= timedelta(days=7)

    r = offer(client, hm, f, dad["id"])  # новый владелец сразу передаёт дальше
    assert r.status_code == 409 and "Следующая передача возможна" in r.json()["detail"]
    r = client.post(f"/api/families/{f}/owner-request", headers=hd)  # «Хочу оплачивать» тоже ждёт неделю
    assert r.status_code == 409
    assert owner_name(client, h, f) == "Мама"

    age_owner_events(session_factory, days=8)
    assert offer(client, hm, f, dad["id"]).status_code == 201  # неделя прошла
    assert accept(client, hd, f).status_code == 200
    assert owner_name(client, h, f) == "Папа"
    check_household_invariants(session_factory)


def test_r23_t5_acceptance_rechecks_the_cooldown(client, owner, session_factory):
    """Предложение сделано, а за это время владельца сменила поддержка: принять нельзя до конца недели."""
    f, (h, u), (hm, mom), (hd, dad) = trio(client, owner)
    assert offer(client, h, f, mom["id"]).status_code == 201
    with session_factory() as db:  # смена владельца без участия людей: в журнале появилась запись «owner» прямо сейчас
        db.add(HouseholdEvent(household_id=db.get(User, u["id"]).household_id, kind="owner", user_id=dad["id"]))
        db.commit()
    r = accept(client, hm, f)
    assert r.status_code == 409 and owner_name(client, h, f) == "Никита"


def test_r23_t6_and_r21_t1_autorenew_is_off_and_paid_days_stay(client, owner, session_factory):
    f, (h, u), (hm, mom), _ = trio(client, owner)
    until = utcnow() + timedelta(days=20)
    with session_factory() as db:
        house = db.get(User, u["id"]).household
        house.plan, house.plus_until = "plus", until
        owner_row = db.get(User, u["id"])
        owner_row.auto_renew, owner_row.pay_method_id, owner_row.renew_period = True, "pm-1", "month"
        db.commit()
    hand_over(client, h, f, mom["id"], hm)
    with session_factory() as db:
        old = db.get(User, u["id"])
        assert (old.auto_renew, old.pay_method_id, old.renew_period) == (False, None, None)
        house = old.household
        assert house.plan == "plus" and households._aware(house.plus_until) == households._aware(until)  # дни остались семье
    check_household_invariants(session_factory)


def test_r23_t7_only_the_owner_offers_and_only_family_members_take_part(client, owner, session_factory):
    f, (h, u), (hm, mom), (hd, dad) = trio(client, owner)
    hs, stranger = register(client, "stranger@example.com", "Чужой")
    assert offer(client, hm, f, dad["id"]).status_code == 403  # участник не предлагает владение
    assert offer(client, hs, f, stranger["id"]).status_code == 404  # чужая семья
    assert client.post(f"/api/families/{f}/owner-request", headers=hs).status_code == 404
    for call in (accept, decline, withdraw):
        assert call(client, hs, f).status_code == 404
    assert offer(client, h, f, stranger["id"]).status_code == 404  # человек не из этой семьи
    assert offer(client, h, f, 99999).status_code == 404
    assert offer(client, h, f, u["id"]).status_code == 404  # самому себе
    assert client.post(f"/api/families/{f}/owner-request", headers=h).status_code == 409  # владелец и так владелец
    assert client.get("/api/auth/me", headers=hs).json()["owner_transfer_waiting"] is False
    check_household_invariants(session_factory)


def test_r23_t8_one_pending_offer_at_a_time_and_withdrawal(client, owner, session_factory):
    f, (h, _), (hm, mom), (hd, dad) = trio(client, owner)
    assert offer(client, h, f, mom["id"]).status_code == 201
    assert offer(client, h, f, dad["id"]).status_code == 409  # пока есть неотвеченное, второе не создаётся
    assert client.post(f"/api/families/{f}/owner-request", headers=hd).status_code == 409
    assert withdraw(client, hm, f).status_code == 404  # забрать может только тот, кто предложил
    r = withdraw(client, h, f)
    assert r.status_code == 200 and r.json()["owner_transfer"] is None
    assert accept(client, hm, f).status_code == 404  # забранное принять нельзя
    assert offer(client, h, f, dad["id"]).status_code == 201  # теперь можно предложить другому
    assert withdraw(client, h, f).status_code == 200
    # просьбу участник тоже может забрать
    assert client.post(f"/api/families/{f}/owner-request", headers=hd).status_code == 201
    assert withdraw(client, h, f).status_code == 404  # забрать её владелец не может (он может только отклонить)
    assert withdraw(client, hd, f).status_code == 200
    with session_factory() as db:
        assert sorted(t.status for t in db.scalars(select(OwnerTransfer))) == ["cancelled", "cancelled", "cancelled"]
    check_household_invariants(session_factory)


def test_r23_t9_pending_offer_is_cancelled_when_the_person_leaves(client, owner, session_factory):
    f, (h, _), (hm, mom), (hd, dad) = trio(client, owner)
    offer(client, h, f, mom["id"])
    assert client.delete(f"/api/families/{f}/members/{mom['id']}", headers=hm).status_code == 204  # Мама ушла
    assert view(client, h, f)["owner_transfer"] is None
    client.post(f"/api/families/{f}/owner-request", headers=hd)
    assert client.delete(f"/api/families/{f}/members/{dad['id']}", headers=h).status_code == 204  # владелец исключил Папу
    assert view(client, h, f)["owner_transfer"] is None
    with session_factory() as db:
        assert [t.status for t in db.scalars(select(OwnerTransfer))] == ["cancelled", "cancelled"]
    check_household_invariants(session_factory)


def test_r23_t9_pending_offer_is_cancelled_when_the_account_is_deleted(client, owner, session_factory):
    f, (h, _), (hm, mom), (hd, _) = trio(client, owner)
    offer(client, h, f, mom["id"])
    r = client.request("DELETE", "/api/auth/me", json={"password": "secret123"}, headers=hm)
    assert r.status_code == 204
    assert view(client, h, f)["owner_transfer"] is None
    check_household_invariants(session_factory)


def test_r23_t9_support_changing_the_owner_cancels_pending_offers(client, owner, session_factory):
    f, (h, u), (hm, mom), (hd, dad) = trio(client, owner)  # Никита и есть администратор: первый аккаунт
    offer(client, h, f, mom["id"])
    r = client.patch(f"/api/admin/families/{f}/members/{dad['id']}", headers=h, json={"role": "owner"})
    assert r.status_code == 200
    assert owner_name(client, h, f) == "Папа"
    assert view(client, h, f)["owner_transfer"] is None
    assert accept(client, hm, f).status_code == 404
    check_household_invariants(session_factory)


def test_r23_t10_unverified_email_cannot_become_owner(client, owner, db, monkeypatch, session_factory):
    f, (h, u), (hm, mom), (hd, dad) = trio(client, owner)
    monkeypatch.setattr(get_settings(), "email_verification", True)
    monkeypatch.setattr(mailer, "deliver", lambda msg: None)
    for uid in (u["id"], dad["id"]):  # владелец и Папа почту подтвердили, Мама нет
        db.get(User, uid).email_verified_at = utcnow()
    db.commit()
    r = offer(client, h, f, mom["id"])
    assert r.status_code == 409 and "почту" in r.json()["detail"]
    assert offer(client, h, f, dad["id"]).status_code == 201
    assert accept(client, hd, f).status_code == 200
    age_owner_events(session_factory)  # неделя прошла: мешает только неподтверждённая почта
    assert client.post(f"/api/families/{f}/owner-request", headers=hm).status_code == 403  # без почты семья ей закрыта
    check_household_invariants(session_factory)


def test_r23_t12_old_offers_are_deleted_30_days_after_the_deadline(client, owner, session_factory):
    f, (h, _), (hm, mom), _ = trio(client, owner)
    offer(client, h, f, mom["id"])
    accept(client, hm, f)
    with session_factory() as db:
        now = datetime.now(timezone.utc)
        assert households.purge_old_transfers(db, now + timedelta(days=24)) == 0  # срок вышел, но 30 дней не прошло
        assert households.purge_old_transfers(db, now + timedelta(days=31)) == 1
        assert db.scalars(select(OwnerTransfer)).all() == []
        assert [e.kind for e in db.scalars(select(HouseholdEvent)) if e.kind == "owner"] == ["owner"]  # журнал остаётся


def test_r23_t12_family_dissolving_removes_its_offers(client, owner, session_factory):
    """Семья из двоих: предложение удаляется вместе с семьёй, когда последний человек уходит (R22)."""
    h, u, f = owner
    hm, mom = register(client, "mom@example.com", "Мама", invite=invite_of(client, h, f))
    offer(client, h, f, mom["id"])
    accept(client, hm, f)  # Мама владелец
    with session_factory() as db:
        assert db.scalar(select(Household.id).where(Household.id == db.get(User, u["id"]).household_id)) is not None
    assert client.request("DELETE", "/api/auth/me", json={"password": "secret123"}, headers=h).status_code == 204
    assert client.request("DELETE", "/api/auth/me", json={"password": "secret123"}, headers=hm).status_code == 204
    with session_factory() as db:
        assert db.scalars(select(OwnerTransfer)).all() == []
        assert db.scalars(select(Household)).all() == []


def test_r23_t13_support_change_is_journaled_mailed_and_stops_autorenew(client, owner, session_factory, monkeypatch):
    """Исключительный случай: администрация меняет владельца без согласия. Запись «кто и когда», письмо всем, автопродление выключено."""
    sent = []
    monkeypatch.setattr(mailer, "deliver", lambda msg: sent.append(msg))
    f, (h, u), (hm, mom), (hd, dad) = trio(client, owner)  # Никита первый аккаунт, поэтому администратор
    with session_factory() as db:
        old = db.get(User, u["id"])
        old.auto_renew, old.pay_method_id, old.renew_period = True, "pm-1", "month"
        db.commit()
    started = offer(client, h, f, mom["id"])  # обычная процедура уже начата
    assert started.status_code == 201
    sent.clear()
    r = client.patch(f"/api/admin/families/{f}/members/{dad['id']}", headers=h, json={"role": "owner"})
    assert r.status_code == 200
    assert owner_name(client, h, f) == "Папа"
    assert view(client, h, f)["owner_transfer"] is None  # начатая процедура отменена
    with session_factory() as db:
        old = db.get(User, u["id"])
        assert (old.auto_renew, old.pay_method_id) == (False, None)  # автопродление выключено, как при обычной передаче (R21)
        e = [e for e in db.scalars(select(HouseholdEvent).where(HouseholdEvent.kind == "owner"))][-1]
        assert (e.user_id, e.actor_id) == (dad["id"], u["id"])  # кому и какой администратор
        assert e.detail == f"прежний владелец: {u['id']}; {households.SUPPORT_OWNER_CHANGE}" and e.created_at is not None
    assert sorted(m["To"] for m in sent) == ["dad@example.com", "mom@example.com", "nikita@example.com"]  # письмо всем людям семьи
    body = sent[0].get_content()
    assert "Папа" in body and "Никита" in body and "http" not in body  # без ссылок: почтовый сервис их отклоняет
    # кулдаун обычной процедуры после смены поддержкой тоже действует, а сама поддержка им не ограничена
    assert offer(client, hd, f, mom["id"]).status_code == 409
    again = client.patch(f"/api/admin/families/{f}/members/{mom['id']}", headers=h, json={"role": "owner"})
    assert again.status_code == 200 and owner_name(client, h, f) == "Мама"
    check_household_invariants(session_factory)


def test_r23_t13_no_email_when_the_owner_does_not_change(client, owner, monkeypatch):
    sent = []
    monkeypatch.setattr(mailer, "deliver", lambda msg: sent.append(msg))
    f, (h, u), _, _ = trio(client, owner)
    sent.clear()
    r = client.patch(f"/api/admin/families/{f}/members/{u['id']}", headers=h, json={"role": "owner"})  # он и так владелец
    assert r.status_code == 200 and sent == []


def test_r23_t13_deleting_an_owner_account_by_support_mails_the_family(client, owner, session_factory, monkeypatch):
    sent = []
    monkeypatch.setattr(mailer, "deliver", lambda msg: sent.append(msg))
    h, u, f = owner
    hm, mom = register(client, "mom@example.com", "Мама", invite=invite_of(client, h, f))
    hs, stranger = register(client, "stranger@example.com", "Чужой")  # владелец собственной семьи
    hm_owner = client.post("/api/families/join", headers=hs, json={"code": invite_of(client, h, f)})
    assert hm_owner.status_code == 200  # Чужой вступил в семью Никиты
    hand_over(client, h, f, mom["id"], hm)  # Мама владелец
    sent.clear()
    r = client.delete(f"/api/admin/users/{mom['id']}", headers=h)  # админ удалил владельца: владение у самого давнего участника
    assert r.status_code == 204
    assert owner_name(client, h, f) == "Никита"
    assert sorted(m["To"] for m in sent) == ["nikita@example.com", "stranger@example.com"]  # удалённому письма нет
    check_household_invariants(session_factory)

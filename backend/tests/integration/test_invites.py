"""Приглашения в семью (R04): одноразовый код на 24 часа, выпускает и видит его только владелец."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app import households, mailer
from app.config import get_settings
from app.models import HouseholdInvite, User, utcnow
from tests.conftest import check_household_invariants, fid, grant_plus, invite_of, register


def enable_billing(client, h):
    assert client.put("/api/admin/billing", headers=h, json={"enabled": True, "trial_days": 0}).status_code == 200


def register_raw(client, code, email="late@example.com"):
    return client.post("/api/auth/register", json={"email": email, "name": "Поздний", "password": "kapsula-secret-123",
                                                    "invite_code": code, "consent": True})


def info(client, code):
    return client.get(f"/api/invites/{code}")


def test_r04_t1_only_owner_sees_and_reissues_the_code(client, owner):
    h1, _, f = owner
    h2, _ = register(client, "mom@example.com", "Мама", invite=invite_of(client, h1, f))
    member_view = client.get(f"/api/families/{f}", headers=h2).json()
    assert member_view["role"] == "member" and member_view["invite_code"] is None and member_view["invite_expires_at"] is None
    assert client.post(f"/api/families/{f}/invite", headers=h2).status_code == 403
    assert client.get(f"/api/families/{f}", headers=h1).json()["invite_code"]  # владелец видит


def test_r04_t2_code_works_once(client, owner, session_factory):
    h1, _, f = owner
    code = invite_of(client, h1, f)
    register(client, "first@example.com", "Первый", invite=code)
    assert register_raw(client, code).status_code == 400  # новый аккаунт с тем же кодом
    hb, _ = register(client, "b@example.com", "Боря")
    assert client.post("/api/families/join", headers=hb, json={"code": code}).status_code == 404  # уже вошедший аккаунт
    assert info(client, code).status_code == 404
    assert len(client.get(f"/api/families/{f}", headers=h1).json()["members"]) == 2

    # у владельца сразу новая ссылка, и по ней тоже один раз
    fresh = invite_of(client, h1, f)
    assert fresh != code
    assert client.post("/api/families/join", headers=hb, json={"code": fresh}).status_code == 200
    hc, _ = register(client, "c@example.com", "Вика")
    assert client.post("/api/families/join", headers=hc, json={"code": fresh}).status_code == 404
    check_household_invariants(session_factory)


def test_r04_t3_expired_and_reissued_codes_do_not_work(client, owner, session_factory):
    h, _, f = owner
    code = invite_of(client, h, f)
    exp = datetime.fromisoformat(client.get(f"/api/families/{f}", headers=h).json()["invite_expires_at"])
    left = (exp if exp.tzinfo else exp.replace(tzinfo=timezone.utc)) - datetime.now(timezone.utc)
    assert timedelta(hours=23, minutes=55) < left <= timedelta(hours=24)

    with session_factory() as db:  # прошло больше суток
        db.scalar(select(HouseholdInvite).where(HouseholdInvite.code == code)).expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    assert info(client, code).status_code == 404
    assert register_raw(client, code).status_code == 400

    fresh = invite_of(client, h, f)  # владельцу выпускается новая ссылка
    assert fresh != code and info(client, fresh).status_code == 200

    new = client.post(f"/api/families/{f}/invite", headers=h).json()["invite_code"]  # перевыпуск одним действием
    assert new not in (code, fresh)
    assert info(client, fresh).status_code == 404 and info(client, new).status_code == 200
    assert client.get(f"/api/families/{f}", headers=h).json()["invite_code"] == new  # действует ровно один код


def test_r04_owner_sees_the_same_valid_code_until_it_is_used(client, owner):
    h, _, f = owner
    assert invite_of(client, h, f) == invite_of(client, h, f)


def test_r04_owner_opening_his_own_link_does_not_burn_it(client, owner):
    h, _, f = owner
    code = invite_of(client, h, f)
    assert client.post("/api/families/join", headers=h, json={"code": code}).json()["role"] == "owner"
    assert info(client, code).status_code == 200


def test_r04_t4_unverified_invitee_frees_the_seat_after_24_hours(client, owner, db, monkeypatch, session_factory):
    """Регистрация закрепила код за человеком; не подтвердил почту за 24 часа: место в семье свободно."""
    h, u, f = owner
    monkeypatch.setattr(get_settings(), "email_verification", True)
    monkeypatch.setattr(mailer, "deliver", lambda msg: None)
    db.get(User, u["id"]).email_verified_at = utcnow()  # владелец почту подтвердил
    db.commit()

    code = invite_of(client, h, f)
    _, lazy = register(client, "lazy@example.com", "Ленивый", invite=code)
    _, quick = register(client, "quick@example.com", "Быстрый", invite=invite_of(client, h, f))
    quick_row = db.get(User, quick["id"])
    quick_row.email_verified_at = utcnow()  # этот подтвердил
    db.commit()
    assert register_raw(client, code, "other@example.com").status_code == 400  # код закреплён за ленивым

    owner_house = db.get(User, u["id"]).household_id
    now = datetime.now(timezone.utc)
    assert households.release_unverified(db, now + timedelta(hours=23)) == 0  # сутки ещё не прошли
    assert households.release_unverified(db, now + timedelta(hours=25)) == 1
    db.expire_all()
    members = {m["name"] for m in client.get(f"/api/families/{f}", headers=h).json()["members"]}
    assert members == {"Никита", "Быстрый"}  # подтвердивший остаётся, владельца не трогаем
    lazy_row = db.get(User, lazy["id"])
    assert lazy_row.household_id != owner_house
    assert len(lazy_row.household.members) == 1 and lazy_row.household.cabinets  # у него своя семья и своя аптечка
    assert households.release_unverified(db, now + timedelta(hours=26)) == 0  # повтор ничего не меняет
    check_household_invariants(session_factory)


def test_r04_t8_old_invite_rows_are_deleted_30_days_after_expiry(client, owner, db):
    """Записи приглашений (код, владелец, вступивший) не хранятся дольше нужного: 30 дней после срока."""
    h, _, f = owner
    used = invite_of(client, h, f)
    register(client, "joined@example.com", "Вступил", invite=used)  # использованный код
    revoked = invite_of(client, h, f)
    fresh = client.post(f"/api/families/{f}/invite", headers=h).json()["invite_code"]  # прежний отозван
    assert fresh != revoked

    def codes():
        db.expire_all()
        return set(db.scalars(select(HouseholdInvite.code)))

    assert {used, revoked, fresh} <= codes()
    now = datetime.now(timezone.utc)
    assert households.purge_old_invites(db, now + timedelta(days=24)) == 0  # срок вышел, но 30 дней не прошло
    assert households.purge_old_invites(db, now + timedelta(days=31)) == 3  # использованный, отозванный и истёкший (действовавший)
    assert codes() == set()
    assert households.purge_old_invites(db, now + timedelta(days=32)) == 0  # повтор ничего не меняет


def test_r04_t8_purge_keeps_the_valid_code(client, owner, db):
    h, _, f = owner
    code = invite_of(client, h, f)
    assert households.purge_old_invites(db) == 0
    assert invite_of(client, h, f) == code


def test_r04_t5_full_family_refuses_and_the_code_survives(client, owner):
    h, _, f = owner
    enable_billing(client, h)
    for i in range(2):  # в бесплатной семье три человека: владелец и двое
        register(client, f"m{i}@example.com", f"Человек {i}", invite=invite_of(client, h, f))
    code = invite_of(client, h, f)
    assert info(client, code).json()["full"] is True
    hz, _ = register(client, "z@example.com", "Зоя")
    r = client.post("/api/families/join", headers=hz, json={"code": code})
    assert r.status_code == 402
    assert info(client, code).status_code == 200 and invite_of(client, h, f) == code  # код не сгорел

    grant_plus(client, h, f)  # владелец подключил Плюс: тот же код работает
    assert info(client, code).json()["full"] is False
    assert client.post("/api/families/join", headers=hz, json={"code": code}).status_code == 200


def test_r04_t6_invite_info_shows_only_what_is_needed(client, owner):
    h, _, f = owner
    code = invite_of(client, h, f)
    body = info(client, code.lower()).json()
    assert body == {"family_name": "Семья Никита", "owner_name": "Никита", "full": False}
    assert info(client, "UNKNOWN1").status_code == 404


def test_r04_admin_list_does_not_expose_invite_codes(client, owner):
    h, _, f = owner
    invite_of(client, h, f)
    rows = client.get("/api/admin/families", headers=h).json()
    assert rows and all("invite_code" not in row for row in rows)


def test_r04_old_cabinet_codes_do_not_work(client, owner, db):
    """Прежние многоразовые коды аптечек (families.invite_code) после перехода на приглашения не принимаются."""
    from app.models import Family

    h, _, f = owner
    legacy = db.get(Family, f).invite_code
    assert info(client, legacy).status_code == 404
    assert register_raw(client, legacy).status_code == 400

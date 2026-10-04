"""Уведомления по расписанию: себе за N минут и повтором, доверенному человеку после согласия."""

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app import mailer
from app.config import get_settings
from app.models import Intake, ScheduleNotified, SchedulePrefs, TrustedContact, User
from app.schedule_notify import GRACE, contact_by_token, due_items, notify_user, run_due, token_for
from app.reminders import MSK
from tests.conftest import register

MON = date(2026, 10, 5)
DUE = datetime(2026, 10, 5, 8, 0, tzinfo=MSK)  # понедельник 08:00 по Москве


def at(minutes_from_due: float) -> datetime:
    return (DUE + timedelta(minutes=minutes_from_due)).astimezone(timezone.utc)


@pytest.fixture
def outbox(monkeypatch):
    monkeypatch.setattr(get_settings(), "smtp_host", "smtp.example.com")
    monkeypatch.setattr(get_settings(), "email_verification", False)
    monkeypatch.setattr(get_settings(), "public_url", "https://kapsulka.test")
    sent = []
    monkeypatch.setattr(mailer, "deliver", sent.append)
    return sent


def body(msg) -> str:
    return msg.get_body(preferencelist=("plain",)).get_content()


@pytest.fixture
def setup(client, outbox):
    h, u = register(client)
    f = u["families"][0]["id"]
    mid = client.post(f"/api/families/{f}/medicines", headers=h,
                      json={"name": "Амепрозол", "unit": "таб", "packages": [{"quantity": 30}]}).json()["id"]
    client.post(f"/api/families/{f}/schedule", headers=h,
                json={"medicine_id": mid, "days": [0], "times": [480], "start_date": MON.isoformat()})
    return h, u, f, mid


def enable(client, h, **extra):
    if extra.get("escalate_enabled"):
        extra.setdefault("escalate_consent", True)  # разрешение сообщать доверенному даётся вместе с включением
    r = client.put("/api/schedule-notifications", headers=h, json={"enabled": True, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def tick(db, user_id, now) -> int:
    db.expire_all()
    return notify_user(db, db.get(User, user_id), db.get(SchedulePrefs, user_id), now)


def add_trusted(client, h, email="mama@example.com", name="Мама"):
    r = client.post("/api/schedule-notifications/trusted", headers=h, json={"name": name, "email": email, "attest": True})
    assert r.status_code == 200, r.text
    return r.json()


def confirm_token(db) -> str:
    db.expire_all()
    return token_for(db.scalar(select(TrustedContact)))


# --- настройки -------------------------------------------------------------------------
def test_defaults_and_validation(client, setup):
    h, *_ = setup
    p = client.get("/api/schedule-notifications", headers=h).json()
    assert p["enabled"] is False and (p["lead_minutes"], p["repeat_minutes"], p["escalate_minutes"]) == (10, 10, 10)
    assert p["trusted"] is None and p["share_medicine_name"] is False
    assert enable(client, h, lead_minutes=15)["lead_minutes"] == 15
    for bad in ({"lead_minutes": 0}, {"lead_minutes": 500}, {"repeat_minutes": 61}, {"enabled": None}):
        assert client.put("/api/schedule-notifications", headers=h, json=bad).status_code == 422


def test_needs_working_mail(client):
    h, _ = register(client)  # почта на сайте не настроена (нет smtp_host)
    assert client.put("/api/schedule-notifications", headers=h, json={"enabled": True}).status_code == 409


# --- себе ------------------------------------------------------------------------------
def test_sequence_before_then_repeat_and_no_duplicates(client, setup, db, outbox):
    h, u, *_ = setup
    enable(client, h)
    assert tick(db, u["id"], at(-20)) == 0 and not outbox                   # рано
    assert tick(db, u["id"], at(-10)) == 1                                  # за 10 минут
    assert "Через 10 минут" in body(outbox[-1]) and "Амепрозол" in body(outbox[-1])
    assert tick(db, u["id"], at(-9)) == 0                                   # второй раз не шлём
    assert tick(db, u["id"], at(5)) == 0
    assert tick(db, u["id"], at(10)) == 1                                   # через 10 минут после: «не отметили»
    assert "не отметили" in outbox[-1]["Subject"]
    assert tick(db, u["id"], at(11)) == 0 and len(outbox) == 2


def test_custom_lead_and_repeat(client, setup, db, outbox):
    h, u, *_ = setup
    enable(client, h, lead_minutes=30, repeat_minutes=5)
    assert tick(db, u["id"], at(-30)) == 1
    assert tick(db, u["id"], at(5)) == 1


def test_taken_in_time_stops_everything(client, setup, db, outbox):
    h, u, f, mid = setup
    enable(client, h)
    client.post(f"/api/families/{f}/medicines/{mid}/consume", headers=h, json={"amount": 1})
    db.query(Intake).update({"taken_at": at(-5), "last_at": at(-5)})  # отметка за 5 минут до приёма
    db.commit()
    assert tick(db, u["id"], at(-10)) == 0 and tick(db, u["id"], at(10)) == 0 and not outbox


def test_taken_after_pre_skips_repeat(client, setup, db, outbox):
    h, u, f, mid = setup
    enable(client, h)
    assert tick(db, u["id"], at(-10)) == 1
    client.post(f"/api/families/{f}/medicines/{mid}/consume", headers=h, json={"amount": 1})
    db.query(Intake).update({"taken_at": at(3), "last_at": at(3)})
    db.commit()
    assert tick(db, u["id"], at(10)) == 0 and len(outbox) == 1


def test_late_run_after_grace_does_not_send(client, setup, db, outbox):
    h, u, *_ = setup
    enable(client, h)
    assert tick(db, u["id"], at(10) + GRACE + timedelta(minutes=1)) == 0  # приложение лежало: запоздало не напоминаем
    assert not outbox


def test_disabled_or_unverified_sends_nothing(client, setup, db, outbox):
    h, u, *_ = setup
    assert run_due(db, at(-10)) == 0  # строки prefs ещё нет
    db.add(SchedulePrefs(user_id=u["id"], enabled=False, lead_minutes=10, repeat_minutes=10, escalate_enabled=False,
                         escalate_minutes=10, share_medicine_name=False))
    db.commit()
    assert run_due(db, at(-10)) == 0 and not outbox


def test_other_day_has_no_occurrence(client, setup, db, outbox):
    h, u, *_ = setup
    enable(client, h)
    tuesday = DUE + timedelta(days=1)
    assert tick(db, u["id"], (tuesday - timedelta(minutes=10)).astimezone(timezone.utc)) == 0


def test_several_medicines_one_letter(client, setup, db, outbox):
    h, u, f, _ = setup
    m2 = client.post(f"/api/families/{f}/medicines", headers=h, json={"name": "Омега-3", "unit": "капс", "packages": [{"quantity": 9}]}).json()["id"]
    client.post(f"/api/families/{f}/schedule", headers=h, json={"medicine_id": m2, "days": [0], "times": [480], "start_date": MON.isoformat()})
    enable(client, h)
    assert tick(db, u["id"], at(-10)) == 1 and len(outbox) == 1
    assert "Амепрозол" in body(outbox[0]) and "Омега-3" in body(outbox[0])
    assert db.scalar(select(ScheduleNotified.id).limit(1)) is not None


def test_plus_required(client, setup, db, outbox):
    h, u, f, _ = setup
    enable(client, h)
    from app.models import AppSetting, Family
    db.add(AppSetting(key="billing", value={"enabled": True}))
    db.commit()  # платная версия включена, у семьи тариф free
    assert tick(db, u["id"], at(-10)) == 0
    r = client.put("/api/schedule-notifications", headers=h, json={"escalate_enabled": True})
    assert r.status_code == 402


# --- доверенный человек ----------------------------------------------------------------
def test_trusted_needs_attest_and_other_email(client, setup):
    h, u, *_ = setup
    r = client.post("/api/schedule-notifications/trusted", headers=h, json={"name": "Мама", "email": "mama@example.com", "attest": False})
    assert r.status_code == 422
    r = client.post("/api/schedule-notifications/trusted", headers=h, json={"name": "Я", "email": u["email"], "attest": True})
    assert r.status_code == 400


def test_request_letter_and_consent_flow(client, setup, db, outbox):
    h, u, *_ = setup
    t = add_trusted(client, h)["trusted"]
    assert t["status"] == "pending" and t["email"] == "mama@example.com"
    letter = outbox[-1]
    assert letter["To"] == "mama@example.com" and "доверенным человеком" in body(letter)
    token = confirm_token(db)
    assert f"https://kapsulka.test/trusted#{token}" in body(letter)
    info = client.post("/api/trusted/lookup", json={"token": token}).json()
    assert info == {"user_name": "Никита", "status": "pending"}  # о человеке видно только имя
    assert client.post("/api/trusted/confirm", json={"token": token}).json()["status"] == "confirmed"
    assert client.get("/api/schedule-notifications", headers=h).json()["trusted"]["status"] == "confirmed"
    row = db.scalar(select(TrustedContact))
    db.refresh(row)
    assert row.confirmed_at and row.consent_version


def test_bad_token_is_404(client, setup, db):
    h, *_ = setup
    add_trusted(client, h)
    token = confirm_token(db)
    for bad in ("x" * 12, "1.deadbeef", "99." + token.split(".")[1], token[:-1] + ("0" if token[-1] != "0" else "1")):
        assert client.post("/api/trusted/lookup", json={"token": bad}).status_code == 404
    assert contact_by_token(db, token) is not None


def test_escalation_only_after_consent(client, setup, db, outbox):
    h, u, *_ = setup
    enable(client, h, escalate_enabled=True)
    add_trusted(client, h)
    outbox.clear()
    tick(db, u["id"], at(-10)); tick(db, u["id"], at(10))
    assert tick(db, u["id"], at(20)) == 0  # он ещё не согласился
    assert [m["To"] for m in outbox] == [u["email"], u["email"]]


def test_escalation_to_confirmed_contact_hides_medicine_by_default(client, setup, db, outbox):
    h, u, *_ = setup
    enable(client, h, escalate_enabled=True)
    add_trusted(client, h)
    client.post("/api/trusted/confirm", json={"token": confirm_token(db)})
    outbox.clear()
    tick(db, u["id"], at(-10)); tick(db, u["id"], at(10))
    assert tick(db, u["id"], at(19)) == 0 and tick(db, u["id"], at(20)) == 1  # +10 повтор, ещё +10 — доверенному
    letter = outbox[-1]
    assert letter["To"] == "mama@example.com"
    text = body(letter)
    assert "Амепрозол" not in text and "08:00" in text and "Никита" in text and "trusted#" in text
    assert tick(db, u["id"], at(21)) == 0


def test_escalation_names_medicine_when_user_allows(client, setup, db, outbox):
    h, u, *_ = setup
    enable(client, h, escalate_enabled=True, share_medicine_name=True)
    add_trusted(client, h)
    client.post("/api/trusted/confirm", json={"token": confirm_token(db)})
    tick(db, u["id"], at(20))
    assert "Амепрозол" in body(outbox[-1])


def test_escalation_off_or_taken_late(client, setup, db, outbox):
    h, u, f, mid = setup
    enable(client, h)  # escalate выключено
    add_trusted(client, h)
    client.post("/api/trusted/confirm", json={"token": confirm_token(db)})
    outbox.clear()
    tick(db, u["id"], at(20))
    assert all(m["To"] != "mama@example.com" for m in outbox)
    client.put("/api/schedule-notifications", headers=h, json={"escalate_enabled": True, "escalate_consent": True})
    client.post(f"/api/families/{f}/medicines/{mid}/consume", headers=h, json={"amount": 1})
    db.query(Intake).update({"taken_at": at(15), "last_at": at(15)})  # успел отметить до письма доверенному
    db.commit()
    outbox.clear()
    assert tick(db, u["id"], at(20)) == 0 and not outbox


def test_decline_and_unsubscribe_stop_letters(client, setup, db, outbox):
    h, u, *_ = setup
    enable(client, h, escalate_enabled=True)
    add_trusted(client, h)
    token = confirm_token(db)
    client.post("/api/trusted/confirm", json={"token": token})
    assert client.post("/api/trusted/decline", json={"token": token}).json()["status"] == "revoked"
    outbox.clear()
    tick(db, u["id"], at(20))
    assert all(m["To"] != "mama@example.com" for m in outbox)
    assert client.post("/api/trusted/confirm", json={"token": token}).status_code == 409  # отказался — сам не вернуть


def test_decline_before_consent(client, setup, db):
    h, *_ = setup
    add_trusted(client, h)
    token = confirm_token(db)
    assert client.post("/api/trusted/decline", json={"token": token}).json()["status"] == "declined"
    assert client.get("/api/schedule-notifications", headers=h).json()["trusted"]["status"] == "declined"


def test_changing_email_invalidates_old_link_and_resets_consent(client, setup, db, outbox):
    h, *_ = setup
    add_trusted(client, h)
    old = confirm_token(db)
    client.post("/api/trusted/confirm", json={"token": old})
    t = add_trusted(client, h, email="papa@example.com", name="Папа")["trusted"]
    assert t["status"] == "pending" and t["email"] == "papa@example.com"
    assert client.post("/api/trusted/lookup", json={"token": old}).status_code == 404
    assert outbox[-1]["To"] == "papa@example.com"


def test_same_email_keeps_consent_and_updates_name(client, setup, db):
    h, *_ = setup
    add_trusted(client, h)
    client.post("/api/trusted/confirm", json={"token": confirm_token(db)})
    t = add_trusted(client, h, name="Мамуля")["trusted"]
    assert t["status"] == "confirmed" and t["name"] == "Мамуля"


def test_remove_trusted_deletes_data(client, setup, db):
    h, u, *_ = setup
    enable(client, h, escalate_enabled=True)
    add_trusted(client, h)
    token = confirm_token(db)
    assert client.delete("/api/schedule-notifications/trusted", headers=h).status_code == 204
    db.expire_all()
    assert db.scalar(select(TrustedContact)) is None
    p = client.get("/api/schedule-notifications", headers=h).json()
    assert p["trusted"] is None and p["escalate_enabled"] is False
    assert client.post("/api/trusted/lookup", json={"token": token}).status_code == 404


def test_deleting_account_deletes_contact(client, setup, db):
    h, u, *_ = setup
    add_trusted(client, h)
    r = client.request("DELETE", "/api/auth/me", headers=h, json={"password": "kapsula-secret-123"})
    assert r.status_code == 204, r.text
    db.expire_all()
    assert db.scalar(select(TrustedContact)) is None


def test_trusted_letters_per_address_are_limited(client, setup, monkeypatch):
    from app.ratelimit import limiter
    monkeypatch.setattr(get_settings(), "rate_limit", True)
    limiter.reset()
    h, *_ = setup
    try:
        for email in ("a@example.com", "b@example.com", "a@example.com", "b@example.com"):
            add_trusted(client, h, email=email)  # на каждый адрес по два письма в сутки
        r = client.post("/api/schedule-notifications/trusted", headers=h, json={"name": "Х", "email": "a@example.com", "attest": True})
        assert r.status_code == 429
    finally:
        limiter.reset()


# --- правки юридического review: разрешение пользователя, стирание данных, оператор в приглашении ---
def test_escalation_needs_users_own_permission(client, setup, db, outbox):
    h, u, *_ = setup
    enable(client, h)
    r = client.put("/api/schedule-notifications", headers=h, json={"escalate_enabled": True})
    assert r.status_code == 422 and "разрешаете" in r.text
    assert client.get("/api/schedule-notifications", headers=h).json()["escalate_consent_at"] is None
    p = client.put("/api/schedule-notifications", headers=h, json={"escalate_enabled": True, "escalate_consent": True}).json()
    assert p["escalate_enabled"] and p["escalate_consent_at"]  # дата сохранена
    assert p["escalate_consent_version"].startswith("share-")  # и редакция текста
    p = client.put("/api/schedule-notifications", headers=h, json={"escalate_enabled": False}).json()
    assert p["escalate_consent_at"] is None and p["escalate_consent_version"] is None  # выключил: разрешение снято, при включении спросим снова
    assert client.put("/api/schedule-notifications", headers=h, json={"escalate_enabled": True}).status_code == 422


def test_no_letter_to_trusted_without_saved_permission(client, setup, db, outbox):
    h, u, *_ = setup
    enable(client, h, escalate_enabled=True)
    add_trusted(client, h)
    client.post("/api/trusted/confirm", json={"token": confirm_token(db)})
    db.expire_all()
    db.get(SchedulePrefs, u["id"]).escalate_consent_at = None  # как если бы дата пропала
    db.commit()
    outbox.clear()
    tick(db, u["id"], at(20))
    assert all(m["To"] != "mama@example.com" for m in outbox)


@pytest.mark.parametrize("action", ["decline", "after_confirm"])
def test_decline_erases_name_and_email(client, setup, db, action):
    h, *_ = setup
    add_trusted(client, h)
    token = confirm_token(db)
    if action == "after_confirm":
        client.post("/api/trusted/confirm", json={"token": token})
    client.post("/api/trusted/decline", json={"token": token})
    db.expire_all()
    row = db.scalar(select(TrustedContact))
    assert row.status in ("declined", "revoked") and row.name == "" and row.email == "" and row.confirmed_at is None
    t = client.get("/api/schedule-notifications", headers=h).json()["trusted"]
    assert t["name"] == "" and t["email"] == ""
    assert client.post("/api/trusted/lookup", json={"token": token}).json()["status"] == row.status  # ссылка всё ещё показывает статус


def test_unanswered_invite_deleted_after_30_days(client, setup, db, outbox):
    h, u, *_ = setup
    enable(client, h)
    add_trusted(client, h)
    now = datetime.now(timezone.utc)
    run_due(db, now + timedelta(days=29))
    db.expire_all()
    assert db.scalar(select(TrustedContact)) is not None
    run_due(db, now + timedelta(days=31))
    db.expire_all()
    assert db.scalar(select(TrustedContact)) is None  # имя и почта удалены


def test_confirmed_contact_is_not_purged(client, setup, db):
    h, *_ = setup
    add_trusted(client, h)
    client.post("/api/trusted/confirm", json={"token": confirm_token(db)})
    from app.schedule_notify import purge_stale_invites
    assert purge_stale_invites(db, datetime.now(timezone.utc) + timedelta(days=90)) == 0


def test_invitation_names_operator(client, setup, outbox):
    h, *_ = setup
    add_trusted(client, h)
    text = body(outbox[-1])
    assert "Оператор: Зименков Никита Вячеславович" in text and "kapsulka.ai@yandex.ru" in text
    assert "https://kapsulka.test/consent-trusted" in text and "через 30 дней" in text

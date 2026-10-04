"""Подтверждение почты при регистрации: письмо с 6-значным кодом, экран-заглушка до его ввода."""

import re
from datetime import datetime, timedelta, timezone

import pytest

from app import households, mailer
from app.config import get_settings
from app.models import User, utcnow
from app.ratelimit import limiter
from tests.conftest import fid, register


@pytest.fixture
def outbox(monkeypatch):
    """Включает проверку почты и собирает письма вместо отправки."""
    monkeypatch.setattr(get_settings(), "email_verification", True)
    monkeypatch.setattr(get_settings(), "public_url", "https://kapsulka.ru")
    sent = []
    monkeypatch.setattr(mailer, "deliver", sent.append)
    return sent


def code_from(msg) -> str:
    text = msg.get_body(preferencelist=("plain",)).get_content()
    assert "http" not in text and "kapsulka.ru" not in text  # ссылок нет: Яндекс режет их как спам
    return re.search(r"^(\d{6})$", text, re.M).group(1)


def verify(client, h, code):
    return client.post("/api/auth/verify-email", headers=h, json={"code": code})


def test_register_sends_letter_and_blocks_until_verified(client, outbox):
    h, u = register(client, "Masha@Example.com", "Маша")
    assert u["verification_needed"] is True and u["email_verified"] is False
    assert len(outbox) == 1 and outbox[0]["To"] == "masha@example.com"
    assert "Код подтверждения" in outbox[0]["Subject"]
    # До подтверждения аптечка закрыта, а профиль виден (чтобы показать экран «Проверьте почту»).
    r = client.get(f"/api/families/{fid(u)}/medicines", headers=h)
    assert r.status_code == 403 and "Подтвердите почту" in r.json()["detail"]
    assert client.get("/api/auth/me", headers=h).status_code == 200

    assert verify(client, h, code_from(outbox[0])).status_code == 204
    me = client.get("/api/auth/me", headers=h).json()
    assert me["email_verified"] is True and me["verification_needed"] is False
    assert client.get(f"/api/families/{fid(u)}/medicines", headers=h).status_code == 200


def test_code_works_once(client, outbox):
    h, _ = register(client)
    code = code_from(outbox[0])
    assert verify(client, h, code).status_code == 204
    r = verify(client, h, code)
    assert r.status_code == 409 and "уже подтверждена" in r.json()["detail"]


def test_wrong_code_rejected(client, outbox):
    h, _ = register(client)
    right = code_from(outbox[0])
    wrong = "000000" if right != "000000" else "111111"
    assert verify(client, h, wrong).status_code == 400
    assert verify(client, h, "abc").status_code == 422
    assert verify(client, h, "12345").status_code == 422
    assert client.post("/api/auth/verify-email", json={"code": right}).status_code == 401  # без входа нельзя


def test_code_stored_only_as_hash(client, outbox, db):
    register(client)
    code = code_from(outbox[0])
    user = db.query(User).one()
    assert user.email_token_hash and code not in user.email_token_hash and len(user.email_token_hash) == 64


def test_expired_code(client, outbox, db):
    h, _ = register(client)
    code = code_from(outbox[0])
    user = db.query(User).one()
    user.email_token_sent_at -= timedelta(minutes=get_settings().email_code_ttl_minutes + 1)
    db.commit()
    r = verify(client, h, code)
    assert r.status_code == 410 and "устарел" in r.json()["detail"]


def test_code_guessing_is_limited(client, outbox, monkeypatch):
    from app.ratelimit import limiter
    monkeypatch.setattr(get_settings(), "rate_limit", True)
    limiter.reset()
    h, _ = register(client)
    right = code_from(outbox[0])
    wrong = "000000" if right != "000000" else "111111"
    assert [verify(client, h, wrong).status_code for _ in range(5)] == [400] * 5
    assert verify(client, h, wrong).status_code == 429
    assert verify(client, h, right).status_code == 429  # после пяти промахов даже верный код ждёт
    limiter.reset()


def test_resend_replaces_old_code(client, outbox):
    h, _ = register(client)
    old = code_from(outbox[0])
    assert client.post("/api/auth/verify-email/resend", headers=h).status_code == 204
    assert len(outbox) == 2
    new = code_from(outbox[1])
    if new != old:
        assert verify(client, h, old).status_code == 400
    assert verify(client, h, new).status_code == 204
    r = client.post("/api/auth/verify-email/resend", headers=h)
    assert r.status_code == 409 and len(outbox) == 2


def test_resend_needs_login(client, outbox):
    assert client.post("/api/auth/verify-email/resend").status_code == 401


def test_resend_is_rate_limited(client, outbox, monkeypatch):
    from app.ratelimit import limiter
    monkeypatch.setattr(get_settings(), "rate_limit", True)
    limiter.reset()
    h, _ = register(client)
    assert client.post("/api/auth/verify-email/resend", headers=h).status_code == 204
    assert client.post("/api/auth/verify-email/resend", headers=h).status_code == 429  # не чаще раза в минуту
    assert len(outbox) == 2
    limiter.reset()


def test_mail_failure_does_not_break_registration(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "email_verification", True)

    def broken(msg):
        raise OSError("SMTP недоступен")
    monkeypatch.setattr(mailer, "deliver", broken)
    h, u = register(client)
    assert u["verification_needed"] is True
    # Письмо можно запросить снова, когда почта заработает.
    assert client.post("/api/auth/verify-email/resend", headers=h).status_code == 204


def test_off_without_smtp(client, monkeypatch):
    """Без SMTP письмо не дойдёт, поэтому проверка по умолчанию выключена и никого не блокирует."""
    sent = []
    monkeypatch.setattr(mailer, "deliver", sent.append)
    assert get_settings().smtp_host == "" and get_settings().email_verification is None
    h, u = register(client)
    assert u["verification_needed"] is False and not sent
    assert client.get(f"/api/families/{fid(u)}/medicines", headers=h).status_code == 200


def test_on_automatically_with_smtp(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "smtp_host", "smtp.example.com")
    sent = []
    monkeypatch.setattr(mailer, "deliver", sent.append)
    _, u = register(client)
    assert u["verification_needed"] is True and len(sent) == 1


def test_letter_escapes_name_in_html(client, outbox):
    register(client, name="<b>Хакер</b>")
    html = outbox[0].get_body(preferencelist=("html",)).get_content()
    assert "<b>Хакер</b>" not in html and "&lt;b&gt;" in html


def test_admin_emails_need_verified_email(client, outbox, monkeypatch):
    """Кто первым зарегистрирует почту из CUREME_ADMIN_EMAILS, админом без подтверждения не станет."""
    register(client)  # первый аккаунт — админ сам по себе
    monkeypatch.setattr(get_settings(), "admin_emails", ["boss@example.com"])
    h, u = register(client, "boss@example.com", "Босс")
    assert client.get("/api/auth/me", headers=h).json()["is_admin"] is False
    verify(client, h, code_from(outbox[-1]))
    assert client.get("/api/auth/me", headers=h).json()["is_admin"] is True


def test_admin_can_mark_verified(client, outbox):
    h_admin, _ = register(client)
    verify(client, h_admin, code_from(outbox[0]))
    h, u = register(client, "masha@example.com", "Маша")
    users = {x["email"]: x for x in client.get("/api/admin/users", headers=h_admin).json()}
    assert users["masha@example.com"]["email_verified"] is False
    r = client.patch(f"/api/admin/users/{u['id']}", headers=h_admin, json={"email_verified": True})
    assert r.status_code == 200 and r.json()["email_verified"] is True
    assert client.get("/api/auth/me", headers=h).json()["verification_needed"] is False


def test_admin_changing_email_vouches_for_it(client, outbox):
    h_admin, _ = register(client)
    verify(client, h_admin, code_from(outbox[0]))
    _, u = register(client, "masha@example.com", "Маша")
    r = client.patch(f"/api/admin/users/{u['id']}", headers=h_admin, json={"email": "maria@example.com"})
    assert r.json()["email_verified"] is True


def test_invited_member_also_verifies(client, outbox):
    h, u = register(client)
    code = client.get(f"/api/families/{fid(u)}", headers=h)
    assert code.status_code == 403  # владелец и сам ещё не подтвердил почту
    verify(client, h, code_from(outbox[0]))
    code = client.get(f"/api/families/{fid(u)}", headers=h).json()["invite_code"]
    h2, u2 = register(client, "mom@example.com", "Мама", invite=code)
    assert u2["verification_needed"] is True
    assert client.get(f"/api/families/{fid(u)}/medicines", headers=h2).status_code == 403


# --- восстановление пароля по коду из письма ---
def reset_code(msg) -> str:
    text = msg.get_body(preferencelist=("plain",)).get_content()
    assert "http" not in text and "kapsulka.ru" not in text  # и здесь без ссылок
    return re.search(r"^(\d{8})$", text, re.M).group(1)


def ask_reset(client, email="masha@example.com"):
    return client.post("/api/auth/password-reset/request", json={"email": email})


def confirm_reset(client, code, password="brand-new-phrase-42", email="masha@example.com"):
    return client.post("/api/auth/password-reset/confirm", json={"email": email, "code": code, "password": password})


def test_password_reset_by_code_changes_password_and_logs_out_old_devices(client, outbox, db):
    h, _ = register(client, "masha@example.com", "Маша", password="old-long-password-1")
    outbox.clear()
    assert ask_reset(client).status_code == 204
    assert len(outbox) == 1 and "Восстановление пароля" in outbox[0]["Subject"]
    code = reset_code(outbox[0])
    assert confirm_reset(client, code).status_code == 204
    assert client.post("/api/auth/login", json={"email": "masha@example.com", "password": "old-long-password-1"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "masha@example.com", "password": "brand-new-phrase-42"}).status_code == 200
    assert client.get("/api/auth/me", headers=h).status_code == 401  # старый вход закрыт
    assert confirm_reset(client, code).status_code == 400  # код одноразовый


def test_password_reset_proves_email_and_unblocks_unverified_account(client, outbox):
    register(client, "masha@example.com", "Маша")
    outbox.clear()
    ask_reset(client)
    assert confirm_reset(client, reset_code(outbox[0])).status_code == 204
    r = client.post("/api/auth/login", json={"email": "masha@example.com", "password": "brand-new-phrase-42"})
    assert r.json()["user"]["email_verified"] is True


def test_password_reset_does_not_reveal_unknown_email(client, outbox):
    assert ask_reset(client, "nobody@example.com").status_code == 204
    assert outbox == []
    assert confirm_reset(client, "12345678", email="nobody@example.com").status_code == 400


def test_password_reset_code_burns_after_5_wrong_tries(client, outbox):
    register(client, "masha@example.com", "Маша")
    outbox.clear()
    ask_reset(client)
    good = reset_code(outbox[0])
    wrong = "00000000" if good != "00000000" else "11111111"
    for _ in range(5):
        assert confirm_reset(client, wrong).status_code == 400
    assert confirm_reset(client, good).status_code == 400  # верный код после пяти промахов уже сгорел
    ask_reset(client)
    assert confirm_reset(client, reset_code(outbox[-1])).status_code == 204  # новый запрос даёт новый код


def test_password_reset_code_expires(client, outbox, db):
    register(client, "masha@example.com", "Маша")
    outbox.clear()
    ask_reset(client)
    row = db.query(User).filter_by(email="masha@example.com").one()
    row.reset_sent_at = utcnow() - timedelta(minutes=31)
    db.commit()
    assert confirm_reset(client, reset_code(outbox[0])).status_code == 400


def test_password_reset_new_code_replaces_old_and_weak_password_is_refused(client, outbox):
    register(client, "masha@example.com", "Маша")
    outbox.clear()
    ask_reset(client)
    ask_reset(client)
    first, second = reset_code(outbox[0]), reset_code(outbox[1])
    assert confirm_reset(client, second, password="12345678").status_code == 422  # слабый пароль код не тратит
    if first != second:
        assert confirm_reset(client, first).status_code == 400
    assert confirm_reset(client, second).status_code == 204


def test_password_reset_admin_needs_16_characters(client, outbox):
    register(client, "admin@example.com", "Админ")  # первый аккаунт: администратор
    outbox.clear()
    ask_reset(client, "admin@example.com")
    code = reset_code(outbox[0])
    short = confirm_reset(client, code, password="short-admin-12", email="admin@example.com")
    assert short.status_code == 422 and "16" in short.text
    assert confirm_reset(client, code, password="long-admin-passphrase", email="admin@example.com").status_code == 204


def test_password_reset_is_rate_limited(client, outbox, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit", True)
    limiter.reset()
    register(client, "masha@example.com", "Маша")
    codes = [ask_reset(client).status_code for _ in range(4)]
    assert codes == [204, 204, 204, 429]  # три письма в час на почту
    limiter.reset()


def test_resend_verification_has_daily_ceiling(client, outbox, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit", True)
    limiter.reset()
    h, _ = register(client, "masha@example.com", "Маша")
    hits = 0
    for _ in range(12):
        for key in [k for k in limiter._hits if k.startswith(("verify-resend-min", "verify-resend-hour"))]:
            limiter._hits.pop(key)  # минутный и часовой лимиты обходим, чтобы дойти до суточного
        r = client.post("/api/auth/verify-email/resend", headers=h)
        hits += r.status_code == 204
    assert hits == 10
    limiter.reset()


# --- уборка неподтверждённых аккаунтов ---
def test_unverified_accounts_are_deleted_after_7_days(client, outbox, db):
    _, boss = register(client, "boss@example.com", "Админ")  # первый аккаунт — администратор
    register(client, "lazy@example.com", "Ленивый")
    _, ok = register(client, "ok@example.com", "Верный")
    for u in (boss, ok):
        db.get(User, u["id"]).email_verified_at = utcnow()
    db.commit()
    now = datetime.now(timezone.utc)
    assert households.purge_unverified_accounts(db, now + timedelta(days=6)) == 0
    assert households.purge_unverified_accounts(db, now + timedelta(days=8)) == 1
    db.expire_all()
    emails = {u.email for u in db.query(User)}
    assert emails == {"boss@example.com", "ok@example.com"}  # подтвердившие остались
    assert households.invariant_problems(db) == []
    assert register(client, "lazy@example.com", "Ленивый")  # почта снова свободна


def test_purge_keeps_admin_and_does_nothing_without_email_verification(client, db, monkeypatch):
    register(client, "admin@example.com", "Админ")  # проверка почты выключена: все аккаунты считаются обычными
    now = datetime.now(timezone.utc) + timedelta(days=30)
    assert households.purge_unverified_accounts(db, now) == 0
    monkeypatch.setattr(get_settings(), "email_verification", True)
    monkeypatch.setattr(mailer, "deliver", lambda msg: None)
    db.get(User, db.query(User).one().id).email_verified_at = None
    db.commit()
    assert households.purge_unverified_accounts(db, now) == 0  # администратора не трогаем

"""Подтверждение почты при регистрации: письмо с 6-значным кодом, экран-заглушка до его ввода."""

import re
from datetime import timedelta

import pytest

from app import mailer
from app.config import get_settings
from app.models import User
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

"""Подтверждение почты при регистрации: письмо со ссылкой, экран-заглушка до перехода по ней."""

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


def token_from(msg) -> str:
    text = msg.get_body(preferencelist=("plain",)).get_content()
    link = next(line for line in text.splitlines() if "/verify-email#" in line)
    assert link.startswith("https://kapsulka.ru/verify-email#")
    return link.rsplit("#", 1)[1]


def test_register_sends_letter_and_blocks_until_verified(client, outbox):
    h, u = register(client, "Masha@Example.com", "Маша")
    assert u["verification_needed"] is True and u["email_verified"] is False
    assert len(outbox) == 1 and outbox[0]["To"] == "masha@example.com"
    assert "Подтвердите почту" in outbox[0]["Subject"]
    # До подтверждения аптечка закрыта, а профиль виден (чтобы показать экран «Проверьте почту»).
    r = client.get(f"/api/families/{fid(u)}/medicines", headers=h)
    assert r.status_code == 403 and "Подтвердите почту" in r.json()["detail"]
    assert client.get("/api/auth/me", headers=h).status_code == 200

    # Ссылку открывают без входа: часто это другой браузер или почтовое приложение.
    assert client.post("/api/auth/verify-email", json={"token": token_from(outbox[0])}).status_code == 204
    me = client.get("/api/auth/me", headers=h).json()
    assert me["email_verified"] is True and me["verification_needed"] is False
    assert client.get(f"/api/families/{fid(u)}/medicines", headers=h).status_code == 200


def test_link_works_once(client, outbox):
    register(client)
    token = token_from(outbox[0])
    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 204
    r = client.post("/api/auth/verify-email", json={"token": token})
    assert r.status_code == 400 and "уже использована" in r.json()["detail"]


def test_wrong_token_rejected(client, outbox):
    register(client)
    assert client.post("/api/auth/verify-email", json={"token": "nope"}).status_code == 400
    assert client.post("/api/auth/verify-email", json={"token": ""}).status_code == 422


def test_token_stored_only_as_hash(client, outbox, db):
    register(client)
    token = token_from(outbox[0])
    user = db.query(User).one()
    assert user.email_token_hash and token not in user.email_token_hash and len(user.email_token_hash) == 64


def test_expired_link(client, outbox, db):
    register(client)
    token = token_from(outbox[0])
    user = db.query(User).one()
    user.email_token_sent_at -= timedelta(hours=get_settings().email_token_ttl_hours, minutes=1)
    db.commit()
    r = client.post("/api/auth/verify-email", json={"token": token})
    assert r.status_code == 410 and "устарела" in r.json()["detail"]


def test_resend_replaces_old_link(client, outbox):
    h, _ = register(client)
    old = token_from(outbox[0])
    assert client.post("/api/auth/verify-email/resend", headers=h).status_code == 204
    assert len(outbox) == 2
    assert client.post("/api/auth/verify-email", json={"token": old}).status_code == 400
    assert client.post("/api/auth/verify-email", json={"token": token_from(outbox[1])}).status_code == 204
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


def test_link_uses_request_host_when_public_url_empty(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "email_verification", True)
    sent = []
    monkeypatch.setattr(mailer, "deliver", sent.append)
    register(client)
    assert "http://testserver/verify-email#" in sent[0].get_body(preferencelist=("plain",)).get_content()


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
    client.post("/api/auth/verify-email", json={"token": token_from(outbox[-1])})
    assert client.get("/api/auth/me", headers=h).json()["is_admin"] is True


def test_admin_can_mark_verified(client, outbox):
    h_admin, _ = register(client)
    client.post("/api/auth/verify-email", json={"token": token_from(outbox[0])})
    h, u = register(client, "masha@example.com", "Маша")
    users = {x["email"]: x for x in client.get("/api/admin/users", headers=h_admin).json()}
    assert users["masha@example.com"]["email_verified"] is False
    r = client.patch(f"/api/admin/users/{u['id']}", headers=h_admin, json={"email_verified": True})
    assert r.status_code == 200 and r.json()["email_verified"] is True
    assert client.get("/api/auth/me", headers=h).json()["verification_needed"] is False


def test_admin_changing_email_vouches_for_it(client, outbox):
    h_admin, _ = register(client)
    client.post("/api/auth/verify-email", json={"token": token_from(outbox[0])})
    _, u = register(client, "masha@example.com", "Маша")
    r = client.patch(f"/api/admin/users/{u['id']}", headers=h_admin, json={"email": "maria@example.com"})
    assert r.json()["email_verified"] is True


def test_invited_member_also_verifies(client, outbox):
    h, u = register(client)
    code = client.get(f"/api/families/{fid(u)}", headers=h)
    assert code.status_code == 403  # владелец и сам ещё не подтвердил почту
    client.post("/api/auth/verify-email", json={"token": token_from(outbox[0])})
    code = client.get(f"/api/families/{fid(u)}", headers=h).json()["invite_code"]
    h2, u2 = register(client, "mom@example.com", "Мама", invite=code)
    assert u2["verification_needed"] is True
    assert client.get(f"/api/families/{fid(u)}/medicines", headers=h2).status_code == 403

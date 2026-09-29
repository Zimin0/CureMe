"""Отправка писем: какой SMTP-режим выбирается и что без SMTP письмо уходит в лог."""

import logging
import smtplib

import pytest

from app import mailer
from app.config import get_settings


class FakeSMTP:
    instances: list["FakeSMTP"] = []

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port, self.context = host, port, context
        self.calls: list = []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.calls.append("quit")

    def starttls(self, context=None):
        self.calls.append("starttls")

    def login(self, user, password):
        self.calls.append(("login", user, password))

    def send_message(self, msg):
        self.calls.append(("send", msg["To"]))


@pytest.fixture(autouse=True)
def mail_log_enabled(monkeypatch):
    # Тесты миграций вызывают logging.fileConfig из alembic/env.py, а он выключает уже созданные логгеры.
    monkeypatch.setattr(mailer.log, "disabled", False)


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.instances = []
    s = get_settings()
    for key, value in {"smtp_host": "smtp.yandex.ru", "smtp_user": "noreply@kapsulka.ru",
                       "smtp_password": "app-password", "mail_from": ""}.items():
        monkeypatch.setattr(s, key, value)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    return s


def test_ssl_port_465(smtp, monkeypatch):
    used = {}
    monkeypatch.setattr(smtplib, "SMTP_SSL", lambda *a, **kw: used.setdefault("ssl", FakeSMTP(*a, **kw)))
    assert mailer.send_mail("masha@example.com", "Тема", "Текст") is True
    conn = used["ssl"]
    assert (conn.host, conn.port) == ("smtp.yandex.ru", 465) and conn.context is not None
    assert conn.calls == [("login", "noreply@kapsulka.ru", "app-password"), ("send", "masha@example.com"), "quit"]


def test_starttls_port_587(smtp, monkeypatch):
    monkeypatch.setattr(smtp, "smtp_security", "starttls")
    monkeypatch.setattr(smtp, "smtp_port", 587)
    assert mailer.send_mail("masha@example.com", "Тема", "Текст")
    conn = FakeSMTP.instances[-1]
    assert conn.port == 587 and conn.calls[0] == "starttls"


def test_sender_defaults_to_smtp_user(smtp):
    msg = mailer.build_message("masha@example.com", "Тема", "Текст", "<p>Текст</p>")
    assert "noreply@kapsulka.ru" in msg["From"] and msg["Message-ID"].endswith("@kapsulka.ru>")
    assert msg.get_body(preferencelist=("html",)).get_content().strip() == "<p>Текст</p>"


def test_failure_returns_false(smtp, monkeypatch, caplog):
    def refuse(*a, **kw):
        raise ConnectionRefusedError("нет соединения")
    monkeypatch.setattr(smtplib, "SMTP_SSL", refuse)
    with caplog.at_level(logging.ERROR, logger="cureme.mail"):
        assert mailer.send_mail("masha@example.com", "Тема", "Текст") is False
    assert "masha@example.com" in caplog.text


def test_without_smtp_letter_goes_to_log(monkeypatch, caplog):
    monkeypatch.setattr(get_settings(), "smtp_host", "")
    with caplog.at_level(logging.WARNING, logger="cureme.mail"):
        assert mailer.send_mail("masha@example.com", "Тема", "Ссылка: https://x/verify-email#abc")
    assert "https://x/verify-email#abc" in caplog.text

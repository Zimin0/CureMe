"""Письма разным получателям: Gmail, Яндекс, mail.ru, адреса с «+», заглавными буквами и кириллицей в имени.

Настоящая почта в тестах не используется: SMTP подменён. Что письма принимает именно Яндекс
и они доходят до Gmail, проверяет «живой» тест внизу, он запускается вручную (см. TESTING.md).
"""

import os
import re
import smtplib
from email.utils import parseaddr

import pytest

from app import email_verification, mailer
from app.config import get_settings

ADDRESSES = [
    "name@gmail.com",
    "Name.Surname@Gmail.com",
    "name+kapsulka@gmail.com",
    "nik.zim2004@googlemail.com",
    "name@yandex.ru",
    "name@ya.ru",
    "name@mail.ru",
    "name@bk.ru",
    "name@outlook.com",
    "name@icloud.com",
    "name@протон.рф",
]


class RecordingSMTP:
    sent: list = []

    def __init__(self, *a, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def login(self, *a):
        pass

    def send_message(self, msg):
        RecordingSMTP.sent.append(msg)


@pytest.fixture
def sent(monkeypatch):
    RecordingSMTP.sent = []
    s = get_settings()
    for key, value in {"smtp_host": "smtp.yandex.ru", "smtp_user": "kapsulka.ai@yandex.ru",
                       "smtp_password": "x", "mail_from": "kapsulka.ai@yandex.ru"}.items():
        monkeypatch.setattr(s, key, value)
    monkeypatch.setattr(smtplib, "SMTP_SSL", RecordingSMTP)
    return RecordingSMTP.sent


@pytest.mark.parametrize("address", ADDRESSES)
def test_verification_letter_for_every_mailbox(sent, address):
    assert email_verification.send_verification(address, "Никита", "123456") is True
    msg = sent[0]
    assert parseaddr(msg["To"])[1] == address
    assert parseaddr(msg["From"])[1] == "kapsulka.ai@yandex.ru"
    # Gmail и Яндекс ждут эти заголовки; без Date письма чаще уходят в спам.
    assert msg["Date"] and msg["Message-ID"] and msg["Subject"]
    assert msg.get_body(preferencelist=("plain",)) and msg.get_body(preferencelist=("html",))


@pytest.mark.parametrize("address", ADDRESSES)
def test_other_letters_for_every_mailbox(sent, address):
    assert mailer.send_mail(address, "Капсулка: проверка", "Текст письма") is True
    assert parseaddr(sent[0]["To"])[1] == address


def test_verification_letter_has_no_links(sent):
    """Яндекс отклонял письма со ссылкой на kapsulka.ru (554 5.7.1), поэтому в письме с кодом их быть не должно."""
    email_verification.send_verification("name@gmail.com", "Никита", "123456")
    msg = sent[0]
    for part in ("plain", "html"):
        body = msg.get_body(preferencelist=(part,)).get_content()
        assert "123456" in body
        assert not re.search(r"https?://|www\.|kapsulka\.ru|href=", body), part


def test_code_is_six_digits_and_varies():
    from app.models import User
    codes = {email_verification.issue_code(User(email="a@b.ru")) for _ in range(30)}
    assert all(re.fullmatch(r"\d{6}", c) for c in codes) and len(codes) > 1


@pytest.mark.skipif(not os.environ.get("CUREME_LIVE_MAIL_TO"),
                    reason="живой тест: задайте CUREME_LIVE_MAIL_TO=ящик1,ящик2 и настройки CUREME_SMTP_*")
def test_live_delivery_to_real_mailboxes():
    """Отправляет настоящее письмо с кодом на каждый ящик из CUREME_LIVE_MAIL_TO.

    Принял ли письмо SMTP-сервер (Яндекс отклоняет спам сразу, ответом 554), видно по результату;
    дошло ли оно до ящика, смотрите в самом ящике.
    """
    assert get_settings().smtp_host, "CUREME_SMTP_HOST не задан"
    targets = [a.strip() for a in os.environ["CUREME_LIVE_MAIL_TO"].split(",") if a.strip()]
    failed = [a for a in targets if not email_verification.send_verification(a, "Тест", "000000")]
    assert not failed, f"SMTP-сервер отклонил письма на: {failed}"

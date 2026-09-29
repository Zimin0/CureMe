"""Отправка писем через SMTP.

SMTP (Simple Mail Transfer Protocol) — стандартный протокол отправки почты: приложение
подключается к почтовому серверу (Яндекс 360, Unisender Go и т. п.), входит по логину
и паролю и передаёт письмо, а доставку до получателя берёт на себя этот сервер.

Пока CUREME_SMTP_HOST не задан (разработка, тесты), письмо не отправляется, а целиком
пишется в лог: ссылку из него можно скопировать оттуда.
"""

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from .config import get_settings

log = logging.getLogger("cureme.mail")
TIMEOUT = 20  # секунд на соединение с SMTP-сервером


def build_message(to: str, subject: str, text: str, html: str | None = None) -> EmailMessage:
    s = get_settings()
    sender = s.mail_from or s.smtp_user or "noreply@localhost"
    msg = EmailMessage()
    msg["From"] = formataddr((s.mail_from_name, sender))
    msg["To"] = to
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid(domain=sender.rpartition("@")[2] or None)
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    return msg


def deliver(msg: EmailMessage) -> None:
    """Передаёт письмо SMTP-серверу. Ошибки не глотает: их ловит send_mail."""
    s = get_settings()
    if not s.smtp_host:
        text = msg.get_body(preferencelist=("plain",)).get_content()
        log.warning("SMTP не настроен (CUREME_SMTP_HOST), письмо на %s не отправлено:\n%s", msg["To"], text)
        return
    context = ssl.create_default_context()
    if s.smtp_security == "ssl":
        smtp = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=TIMEOUT, context=context)
    else:
        smtp = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=TIMEOUT)
    with smtp:
        if s.smtp_security == "starttls":
            smtp.starttls(context=context)
        if s.smtp_user:
            smtp.login(s.smtp_user, s.smtp_password)
        smtp.send_message(msg)


def send_mail(to: str, subject: str, text: str, html: str | None = None) -> bool:
    """Отправляет письмо; False, если не получилось (причина — в логе).

    Вызывается в фоне (BackgroundTasks), после ответа на запрос: человек не ждёт SMTP-сервер,
    а сбой почты не превращает регистрацию в ошибку 500.
    """
    try:
        deliver(build_message(to, subject, text, html))
        return True
    except (OSError, smtplib.SMTPException):
        log.exception("Не удалось отправить письмо на %s", to)
        return False


if __name__ == "__main__":
    # Проверка настроек SMTP на сервере: python -m app.mailer you@example.com
    import sys

    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) != 2:
        sys.exit("Использование: python -m app.mailer адрес@почты")
    if not get_settings().smtp_host:
        sys.exit("CUREME_SMTP_HOST не задан: письмо не уйдёт. Впишите настройки почты в .env")
    ok = send_mail(sys.argv[1], "Проверка почты Капсулки", "Если вы читаете это письмо, отправка почты настроена правильно.")
    print("Письмо отправлено" if ok else "Не получилось, причина выше")
    sys.exit(0 if ok else 1)

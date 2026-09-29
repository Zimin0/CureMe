"""Подтверждение почты: одноразовая ссылка в письме.

Токен — 32 случайных байта (secrets.token_urlsafe). В базе хранится только его SHA-256:
по хешу нельзя восстановить ссылку, поэтому утечка копии базы не позволит подтвердить
чужую почту. Токен стоит в ссылке после «#»: эту часть адреса браузер не отправляет
на сервер, и она не попадает в логи Caddy. Новое письмо заменяет старый токен,
а переход по ссылке его стирает — ссылка работает один раз.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from html import escape

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .mailer import send_mail
from .models import User, utcnow


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def needs_verification(user: User) -> bool:
    """Пускать ли человека в аптечку только после перехода по ссылке из письма."""
    return get_settings().email_verification_required and user.email_verified_at is None


def mark_verified(user: User) -> None:
    user.email_verified_at = utcnow()
    user.email_token_hash = user.email_token_sent_at = None


def issue_token(user: User) -> str:
    token = secrets.token_urlsafe(32)
    user.email_token_hash = hash_token(token)
    user.email_token_sent_at = utcnow()
    return token


def _aware(dt: datetime) -> datetime:
    # SQLite возвращает время без часового пояса, хотя записывали в UTC.
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def user_by_token(db: Session, token: str) -> tuple[User | None, bool]:
    """(пользователь, ссылка просрочена). Пользователя нет — ссылка неверная или уже использована."""
    user = db.scalar(select(User).where(User.email_token_hash == hash_token(token)))
    if not user or not user.email_token_sent_at:
        return None, False
    ttl = timedelta(hours=get_settings().email_token_ttl_hours)
    return user, _aware(user.email_token_sent_at) + ttl < datetime.now(timezone.utc)


def verification_link(request: Request, token: str) -> str:
    # Адрес сайта берём из настроек, а не из заголовка Host: иначе подделанный Host
    # мог бы отправить человеку письмо со ссылкой на чужой сайт.
    base = get_settings().public_url or str(request.base_url)
    return f"{base.rstrip('/')}/verify-email#{token}"


def send_verification(to: str, name: str, link: str) -> bool:
    hours = get_settings().email_token_ttl_hours
    text = (
        f"Здравствуйте, {name}!\n\n"
        "Чтобы закончить регистрацию в Капсулке, подтвердите почту — откройте ссылку:\n"
        f"{link}\n\n"
        f"Ссылка действует {hours} ч. Если вы не регистрировались, просто удалите это письмо: "
        "без подтверждения аккаунт не заработает.\n\n— Капсулка, домашняя аптечка"
    )
    html = f"""\
<div style="font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:480px;margin:0 auto;color:#1f2937">
  <h2 style="margin:0 0 16px">Подтвердите почту</h2>
  <p>Здравствуйте, {escape(name)}!</p>
  <p>Чтобы закончить регистрацию в Капсулке, нажмите кнопку:</p>
  <p style="margin:24px 0"><a href="{escape(link)}"
     style="background:#0f9d8a;color:#fff;padding:12px 20px;border-radius:10px;text-decoration:none;display:inline-block">
     Подтвердить почту</a></p>
  <p style="font-size:14px;color:#6b7280">Или откройте ссылку: <br><a href="{escape(link)}">{escape(link)}</a></p>
  <p style="font-size:14px;color:#6b7280">Ссылка действует {hours} ч. Если вы не регистрировались,
     просто удалите это письмо: без подтверждения аккаунт не заработает.</p>
</div>"""
    return send_mail(to, "Подтвердите почту в Капсулке", text, html)

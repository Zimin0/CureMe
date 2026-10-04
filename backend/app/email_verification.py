"""Подтверждение почты: 6-значный код в письме.

Код вводят на сайте, поэтому в письме нет ссылки: почтовый фильтр Яндекса отклонял
письма со ссылкой на новый домен как спам. В базе хранится только SHA-256 от пары
«почта + код»: утечка копии базы не позволит подтвердить чужую почту. Новое письмо
заменяет старый код, успешный ввод его стирает.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from html import escape

from .config import get_settings
from .mailer import send_mail
from .models import User, utcnow


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def hash_code(email: str, code: str) -> str:
    return hashlib.sha256(f"{email.lower()}:{code}".encode()).hexdigest()


def needs_verification(user: User) -> bool:
    """Пускать ли человека в аптечку только после ввода кода из письма."""
    return get_settings().email_verification_required and user.email_verified_at is None


def mark_verified(user: User) -> None:
    user.email_verified_at = utcnow()
    user.email_token_hash = user.email_token_sent_at = None


def issue_code(user: User) -> str:
    code = f"{secrets.randbelow(10**6):06d}"
    user.email_token_hash = hash_code(user.email, code)
    user.email_token_sent_at = utcnow()
    return code


def _aware(dt: datetime) -> datetime:
    # SQLite возвращает время без часового пояса, хотя записывали в UTC.
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def code_matches(user: User, code: str) -> tuple[bool, bool]:
    """(код верный, код просрочен)."""
    if not user.email_token_hash or not user.email_token_sent_at:
        return False, False
    if not secrets.compare_digest(user.email_token_hash, hash_code(user.email, code)):
        return False, False
    ttl = timedelta(minutes=get_settings().email_code_ttl_minutes)
    return True, _aware(user.email_token_sent_at) + ttl < datetime.now(timezone.utc)


def send_verification(to: str, name: str, code: str) -> bool:
    minutes = get_settings().email_code_ttl_minutes
    text = (
        f"Здравствуйте, {name}!\n\n"
        "Чтобы закончить регистрацию в Капсулке, введите на сайте код подтверждения:\n\n"
        f"{code}\n\n"
        f"Код действует {minutes} мин. Если вы не регистрировались, просто удалите это письмо: "
        "без подтверждения аккаунт не заработает.\n\n— Капсулка, домашняя аптечка"
    )
    html = f"""\
<div style="font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:480px;margin:0 auto;color:#1f2937">
  <h2 style="margin:0 0 16px">Код подтверждения</h2>
  <p>Здравствуйте, {escape(name)}!</p>
  <p>Чтобы закончить регистрацию в Капсулке, введите на сайте этот код:</p>
  <p style="margin:24px 0;font-size:32px;font-weight:700;letter-spacing:8px;color:#0f9d8a">{code}</p>
  <p style="font-size:14px;color:#6b7280">Код действует {minutes} мин. Если вы не регистрировались,
     просто удалите это письмо: без подтверждения аккаунт не заработает.</p>
</div>"""
    return send_mail(to, "Код подтверждения Капсулки", text, html)


# --- восстановление пароля ---
# Тот же приём, что и для подтверждения почты: в письме код, а не ссылка (Яндекс отклонял письма со ссылкой на новый
# домен). Код из 8 цифр, 30 минут жизни, после 5 неверных вводов сгорает, успешный ввод его стирает. Код в базе
# хранится только хешем, а ввод пароля по коду заодно доказывает, что человек владеет почтой.
RESET_MAX_ATTEMPTS = 5


def issue_reset_code(user: User) -> str:
    code = f"{secrets.randbelow(10**8):08d}"
    user.reset_code_hash = hash_code("reset:" + user.email, code)
    user.reset_sent_at = utcnow()
    user.reset_attempts = 0
    return code


def clear_reset(user: User) -> None:
    user.reset_code_hash = user.reset_sent_at = None
    user.reset_attempts = 0


def reset_code_ok(user: User, code: str) -> bool:
    """Проверяет код сброса. Неверный ввод тратит попытку; на пятой код сгорает (его нужно запросить заново)."""
    if not user.reset_code_hash or not user.reset_sent_at:
        return False
    ttl = timedelta(minutes=get_settings().email_code_ttl_minutes)
    if _aware(user.reset_sent_at) + ttl < datetime.now(timezone.utc):
        clear_reset(user)
        return False
    if secrets.compare_digest(user.reset_code_hash, hash_code("reset:" + user.email, code)):
        return True
    user.reset_attempts += 1
    if user.reset_attempts >= RESET_MAX_ATTEMPTS:
        clear_reset(user)
    return False


def send_password_reset(to: str, name: str, code: str) -> bool:
    minutes = get_settings().email_code_ttl_minutes
    text = (
        f"Здравствуйте, {name}!\n\n"
        "Кто-то попросил восстановить пароль от Капсулки. Введите на сайте этот код и новый пароль:\n\n"
        f"{code}\n\n"
        f"Код действует {minutes} мин. Если это были не вы, просто удалите письмо: пароль не изменится, "
        "а чужой человек без кода в аккаунт не попадёт.\n\n— Капсулка, домашняя аптечка"
    )
    html = f"""\
<div style="font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:480px;margin:0 auto;color:#1f2937">
  <h2 style="margin:0 0 16px">Восстановление пароля</h2>
  <p>Здравствуйте, {escape(name)}!</p>
  <p>Кто-то попросил восстановить пароль от Капсулки. Введите на сайте этот код и новый пароль:</p>
  <p style="margin:24px 0;font-size:32px;font-weight:700;letter-spacing:8px;color:#0f9d8a">{code}</p>
  <p style="font-size:14px;color:#6b7280">Код действует {minutes} мин. Если это были не вы, просто удалите письмо:
     пароль не изменится, а чужой человек без кода в аккаунт не попадёт.</p>
</div>"""
    return send_mail(to, "Восстановление пароля Капсулки", text, html)

"""Telegram-бот Капсулки: привязка аккаунта и отправка напоминаний.

Bot API — HTTP-интерфейс Telegram для ботов: https://api.telegram.org/bot<токен>/<метод>.
Бота создаёт владелец сайта в @BotFather и кладёт токен в CUREME_TELEGRAM_BOT_TOKEN.

Как человек привязывает Telegram: в приложении жмёт «Подключить Telegram», получает ссылку
t.me/<бот>?start=<код>. Telegram открывает чат с ботом и присылает боту «/start <код>».
Бот находит аккаунт по хешу кода и запоминает chat_id — куда потом слать напоминания.

Сообщения бот забирает сам (long polling, метод getUpdates), а не ждёт их на адрес сайта
(webhook): так не нужно открывать наружу ещё один адрес и настраивать его в Telegram.
Long polling — запрос «отдай новые сообщения», который сервер Telegram держит открытым
до 50 секунд, пока сообщение не придёт. На сервере один процесс uvicorn, поэтому опрашивает
ровно один поток.
"""

import logging
import secrets
import threading
from datetime import datetime, timedelta, timezone
from html import escape

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .email_verification import hash_token
from .services import telegram_active
from .models import NotificationPrefs, User, utcnow

log = logging.getLogger("cureme.telegram")
# httpx пишет в лог адрес каждого запроса, а в адресе Bot API стоит токен бота.
logging.getLogger("httpx").setLevel(logging.WARNING)
API = "https://api.telegram.org"
POLL_TIMEOUT = 50  # секунд держит запрос getUpdates


class TelegramError(Exception):
    pass


def call(method: str, http_timeout: float = 20, **params) -> dict:
    """Вызов метода Bot API. Ошибку сети или ответ ok=false превращает в TelegramError."""
    token = get_settings().telegram_bot_token
    params = {k: v for k, v in params.items() if v is not None}
    try:
        r = httpx.post(f"{API}/bot{token}/{method}", json=params, timeout=http_timeout)
        data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        raise TelegramError(f"{method}: {type(e).__name__}") from None  # в тексте ошибки httpx есть токен
    if not data.get("ok"):
        raise TelegramError(f"{method}: {data.get('error_code')} {data.get('description')}")
    return data.get("result")


def send_message(chat_id: int, html: str) -> bool:
    """Отправляет сообщение (разметка HTML). False, если не получилось (причина — в логе)."""
    if not get_settings().telegram_enabled:
        log.warning("Telegram не настроен, сообщение в чат %s не отправлено:\n%s", chat_id, html)
        return False
    try:
        call("sendMessage", chat_id=chat_id, text=html, parse_mode="HTML", link_preview_options={"is_disabled": True})
        return True
    except TelegramError:
        log.exception("Не удалось отправить сообщение в Telegram (чат %s)", chat_id)
        return False


# --- привязка аккаунта ---

def link_url(prefs: NotificationPrefs) -> str:
    """Новая одноразовая ссылка на бота. Старая перестаёт работать."""
    code = secrets.token_urlsafe(24)  # Telegram разрешает в start-параметре до 64 символов A-Z a-z 0-9 _ -
    prefs.telegram_code_hash = hash_token(code)
    prefs.telegram_code_sent_at = utcnow()
    return f"https://t.me/{get_settings().telegram_bot_username}?start={code}"


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def link_chat(db: Session, code: str, chat_id: int, username: str | None) -> User | None:
    """Привязывает чат к аккаунту по коду из ссылки. None — код неверный, использован или просрочен."""
    prefs = db.scalar(select(NotificationPrefs).where(NotificationPrefs.telegram_code_hash == hash_token(code)))
    if not prefs or not prefs.telegram_code_sent_at:
        return None
    ttl = timedelta(minutes=get_settings().telegram_link_ttl_minutes)
    if _aware(prefs.telegram_code_sent_at) + ttl < datetime.now(timezone.utc):
        return None
    # Этот чат был привязан к другому аккаунту — отвязываем там: один чат, один аккаунт.
    other = db.scalar(select(NotificationPrefs).where(NotificationPrefs.telegram_chat_id == chat_id))
    if other and other.user_id != prefs.user_id:
        other.telegram_chat_id = other.telegram_name = None
        other.telegram_enabled = False
        db.flush()
    prefs.telegram_chat_id = chat_id
    prefs.telegram_name = f"@{username}" if username else None
    prefs.telegram_enabled = True
    prefs.telegram_code_hash = prefs.telegram_code_sent_at = None
    db.commit()
    return db.get(User, prefs.user_id)


def unlink_chat(db: Session, chat_id: int) -> bool:
    prefs = db.scalar(select(NotificationPrefs).where(NotificationPrefs.telegram_chat_id == chat_id))
    if not prefs:
        return False
    prefs.telegram_chat_id = prefs.telegram_name = None
    prefs.telegram_enabled = False
    db.commit()
    return True


HELP = (
    "Это бот <b>Капсулки</b>: он присылает напоминания, когда лекарство заканчивается "
    "или у него истекает срок годности.\n\n"
    "Чтобы подключить бота, откройте Капсулку → «Семья» → «Напоминания» → «Подключить Telegram».\n"
    "Отключить: команда /stop или кнопка «Отключить» там же."
)


def handle_update(db: Session, update: dict) -> str | None:
    """Разбирает одно входящее сообщение и возвращает ответ бота (или None — отвечать не нужно)."""
    msg = update.get("message") or {}
    chat = msg.get("chat") or {}
    text = (msg.get("text") or "").strip()
    if chat.get("type") != "private" or not text:
        return None  # в группах бот молчит: напоминания личные
    chat_id = chat["id"]
    if text.startswith("/start"):
        code = text.partition(" ")[2].strip()
        if not code:
            return HELP
        user = link_chat(db, code, chat_id, (msg.get("from") or {}).get("username"))
        if not user:
            return "Ссылка не подошла: она одноразовая и действует час. Получите новую в Капсулке → «Семья» → «Напоминания»."
        return (f"Готово, {escape(user.name)}! Telegram подключён к Капсулке. "
                "Напоминания о лекарствах будут приходить сюда.\nОтключить: /stop")
    if text.startswith("/stop"):
        if unlink_chat(db, chat_id):
            return "Telegram отключён от Капсулки, напоминаний сюда больше не будет."
        return "Этот чат и так не подключён к Капсулке."
    return HELP


def poll_forever(session_factory, stop: threading.Event) -> None:
    """Фоновый поток: забирает сообщения боту и отвечает на них."""
    offset = None
    while not stop.is_set():
        with session_factory() as db:
            on = telegram_active(db)
        if not on:  # админ выключил Telegram: бота не опрашиваем, ждём минуту и смотрим снова
            stop.wait(60)
            continue
        try:
            updates = call("getUpdates", http_timeout=POLL_TIMEOUT + 10, offset=offset,
                           timeout=POLL_TIMEOUT, allowed_updates=["message"])
        except TelegramError:
            log.exception("Telegram getUpdates не ответил, пробую через минуту")
            stop.wait(60)
            continue
        for upd in updates or []:
            offset = upd["update_id"] + 1
            with session_factory() as db:
                try:
                    answer = handle_update(db, upd)
                except Exception:  # noqa: BLE001 — одно кривое сообщение не должно остановить бота
                    log.exception("Ошибка при разборе сообщения Telegram")
                    db.rollback()
                    continue
            if answer:
                send_message(upd["message"]["chat"]["id"], answer)


if __name__ == "__main__":
    # Проверка бота на сервере: python -m app.telegram  (или python -m app.telegram <chat_id> — пробное сообщение)
    import sys

    logging.basicConfig(level=logging.INFO)
    if not get_settings().telegram_enabled:
        sys.exit("CUREME_TELEGRAM_BOT_TOKEN или CUREME_TELEGRAM_BOT_USERNAME не заданы. Впишите их в .env")
    try:
        me = call("getMe")
    except TelegramError as e:
        sys.exit(f"Бот не отвечает: {e}")
    print(f"Бот работает: @{me['username']}")
    if me["username"].lower() != get_settings().telegram_bot_username.lower():
        print(f"Внимание: в CUREME_TELEGRAM_BOT_USERNAME указано {get_settings().telegram_bot_username}")
    if len(sys.argv) == 2:
        print("Сообщение отправлено" if send_message(int(sys.argv[1]), "Проверка бота Капсулки") else "Не получилось, причина выше")

"""Напоминания «скоро закончится» и «истекает срок»: настройки, рассылка, Telegram-бот, тариф."""

from datetime import date, datetime, timedelta, timezone

import pytest

from app import mailer, reminders, telegram
from app.config import get_settings
from app.models import NotificationPrefs, ReminderSent, User
from tests.conftest import fid, register

TODAY = date(2026, 10, 1)


@pytest.fixture
def outbox(monkeypatch):
    """Почта «настроена» (без проверки адреса), письма складываются сюда."""
    monkeypatch.setattr(get_settings(), "smtp_host", "smtp.example.com")
    monkeypatch.setattr(get_settings(), "email_verification", False)
    sent = []
    monkeypatch.setattr(mailer, "deliver", sent.append)
    return sent


@pytest.fixture
def tg(monkeypatch):
    """Telegram-бот «настроен», вызовы Bot API складываются сюда."""
    monkeypatch.setattr(get_settings(), "telegram_bot_token", "123:TEST")
    monkeypatch.setattr(get_settings(), "telegram_bot_username", "kapsulka_bot")
    calls = []

    def fake_call(method, http_timeout=20, **params):
        calls.append((method, params))
        return {}
    monkeypatch.setattr(telegram, "call", fake_call)
    return calls


def text_of(msg) -> str:
    return msg.get_body(preferencelist=("plain",)).get_content()


def add(client, h, f, name, qty, expiry=None, min_quantity=None):
    pkg = {"quantity": qty, "expiry_date": expiry.isoformat() if expiry else None}
    r = client.post(f"/api/families/{f}/medicines", headers=h,
                    json={"name": name, "min_quantity": min_quantity, "packages": [pkg]})
    assert r.status_code == 201, r.text
    return r.json()


def remind(db, user_id, today=TODAY, kinds=None, now=None) -> int:
    db.expire_all()
    # по умолчанию «сейчас» — через сутки: только что добавленные упаковки уже не новые
    now = now or datetime.now(timezone.utc) + timedelta(days=1)
    return reminders.remind_user(db, db.get(User, user_id), today, kinds=kinds, now=now)


@pytest.fixture
def home(client, outbox):
    h, u = register(client)
    f = fid(u)
    r = client.put("/api/notifications", headers=h, json={"email_enabled": True})
    assert r.status_code == 200, r.text
    return h, u, f


def test_defaults_before_setup(client):
    h, _ = register(client)
    p = client.get("/api/notifications", headers=h).json()
    assert p["available"] is True  # платная версия выключена — доступно всем
    assert p["email_enabled"] is False and p["telegram_enabled"] is False
    assert p["notify_low"] is True and p["notify_expiry"] is True and p["expiry_days"] == 30
    assert p["email_possible"] is False and p["telegram_possible"] is False  # на сайте ни почты, ни бота


def test_email_needs_smtp(client):
    h, _ = register(client)
    r = client.put("/api/notifications", headers=h, json={"email_enabled": True})
    assert r.status_code == 409


def test_one_digest_then_silence(client, db, home, outbox):
    h, u, f = home
    add(client, h, f, "Нурофен", 3, min_quantity=5)                                # заканчивается
    add(client, h, f, "Парацетамол", 10, expiry=TODAY + timedelta(days=10))       # скоро истекает
    add(client, h, f, "Лоратадин", 4, expiry=TODAY - timedelta(days=3))           # истёк
    add(client, h, f, "Витамин D", 50, expiry=TODAY + timedelta(days=200), min_quantity=5)  # всё хорошо

    assert remind(db, u["id"]) == 3
    assert len(outbox) == 1
    body = text_of(outbox[0])
    assert outbox[0]["To"] == "nikita@example.com"
    assert "Нурофен: осталось 3 шт" in body
    assert "Парацетамол: годен до 11.10.2026, осталось 10 дней" in body
    assert "Лоратадин: срок истёк 28.09.2026" in body
    assert "Витамин D" not in body
    assert body.index("Срок годности истёк") < body.index("Скоро истекает") < body.index("Заканчиваются")

    # Назавтра то же самое не повторяем.
    assert remind(db, u["id"], TODAY + timedelta(days=1)) == 0
    assert len(outbox) == 1


def test_new_package_waits_12_hours(client, db, home, outbox):
    h, u, f = home
    add(client, h, f, "Лоратадин", 4, expiry=TODAY - timedelta(days=3))
    add(client, h, f, "Аспирин", 4, expiry=TODAY - timedelta(days=1))
    soon = datetime.now(timezone.utc) + timedelta(hours=11)
    assert remind(db, u["id"], now=soon) == 0 and not outbox
    later = datetime.now(timezone.utc) + timedelta(hours=13)
    assert remind(db, u["id"], now=later) == 2
    assert len(outbox) == 1  # одно сообщение на все просроченные
    body = text_of(outbox[0])
    assert "Лоратадин" in body and "Аспирин" in body


def test_new_package_low_stock_not_delayed(client, db, home, outbox):
    h, u, f = home
    add(client, h, f, "Нурофен", 3, min_quantity=5)
    assert remind(db, u["id"], now=datetime.now(timezone.utc)) == 1


def test_family_nudge_sends_only_low(client, db, home, outbox):
    h, u, f = home
    add(client, h, f, "Нурофен", 3, min_quantity=5)
    add(client, h, f, "Лоратадин", 4, expiry=TODAY - timedelta(days=3))
    assert remind(db, u["id"], kinds={"low"}) == 1
    assert "Лоратадин" not in text_of(outbox[0])
    assert remind(db, u["id"]) == 1  # срок — в ежедневной сводке


def test_low_again_after_restock(client, db, home, outbox):
    h, u, f = home
    med = add(client, h, f, "Нурофен", 3, min_quantity=5)
    pkg = med["packages"][0]["id"]
    assert remind(db, u["id"]) == 1
    # Пополнили — повод пропал, запись забыта.
    client.patch(f"/api/families/{f}/medicines/{med['id']}/packages/{pkg}", headers=h, json={"quantity": 20})
    assert remind(db, u["id"]) == 0
    assert db.query(ReminderSent).count() == 0
    # Снова заканчивается — снова напоминаем.
    client.patch(f"/api/families/{f}/medicines/{med['id']}/packages/{pkg}", headers=h, json={"quantity": 2})
    assert remind(db, u["id"]) == 1
    assert len(outbox) == 2 and "осталось 2 шт" in text_of(outbox[1])


def test_expiring_then_expired_are_two_reminders(client, db, home, outbox):
    h, u, f = home
    add(client, h, f, "Парацетамол", 10, expiry=TODAY + timedelta(days=2))
    assert remind(db, u["id"]) == 1
    assert remind(db, u["id"], TODAY + timedelta(days=1)) == 0
    assert remind(db, u["id"], TODAY + timedelta(days=3)) == 1
    assert "срок истёк" in text_of(outbox[-1])


def test_kinds_and_days_follow_settings(client, db, home, outbox):
    h, u, f = home
    add(client, h, f, "Нурофен", 3, min_quantity=5)
    add(client, h, f, "Парацетамол", 10, expiry=TODAY + timedelta(days=10))
    client.put("/api/notifications", headers=h, json={"notify_low": False, "expiry_days": 7})
    assert remind(db, u["id"]) == 0  # о запасах не просили, а до срока ещё 10 дней > 7
    client.put("/api/notifications", headers=h, json={"expiry_days": 14})
    assert remind(db, u["id"]) == 1 and "Парацетамол" in text_of(outbox[-1])


def test_no_threshold_no_low_reminder(client, db, home, outbox):
    h, u, f = home
    add(client, h, f, "Нурофен", 1)
    assert remind(db, u["id"]) == 0 and outbox == []


def test_nothing_recorded_when_delivery_fails(client, db, home, monkeypatch):
    h, u, f = home
    add(client, h, f, "Нурофен", 3, min_quantity=5)

    def broken(msg):
        raise OSError("SMTP недоступен")
    monkeypatch.setattr(mailer, "deliver", broken)
    assert remind(db, u["id"]) == 0
    assert db.query(ReminderSent).count() == 0  # завтра попробуем снова


def test_whole_family_gets_it_by_their_own_settings(client, db, outbox):
    h, u = register(client)
    f = fid(u)
    code = client.get(f"/api/families/{f}", headers=h).json()["invite_code"]
    h2, mom = register(client, "mom@example.com", "Мама", invite=code)
    add(client, h, f, "Нурофен", 3, min_quantity=5)
    client.put("/api/notifications", headers=h2, json={"email_enabled": True})  # включила только мама
    db.expire_all()
    assert reminders.run_family(db, f) == 1
    assert [m["To"] for m in outbox] == ["mom@example.com"]


def test_several_families_are_named(client, db, home, outbox):
    h, u, f = home
    other = client.post("/api/families", headers=h, json={"name": "Дача"}).json()
    add(client, h, f, "Нурофен", 3, min_quantity=5)
    add(client, h, other["id"], "Бинт", 1, min_quantity=2)
    assert remind(db, u["id"]) == 2
    assert "Бинт (Дача): осталось 1 шт" in text_of(outbox[0])


# --- тариф ---

def test_free_family_gets_nothing_when_billing_on(client, db, home, outbox):
    h, u, f = home
    add(client, h, f, "Нурофен", 3, min_quantity=5)
    assert client.put("/api/admin/billing", headers=h, json={"enabled": True}).status_code == 200
    assert remind(db, u["id"]) == 0 and outbox == []
    p = client.get("/api/notifications", headers=h).json()
    assert p["available"] is False
    r = client.put("/api/notifications", headers=h, json={"email_enabled": True})
    assert r.status_code == 402 and r.headers["X-Plus-Feature"] == "reminders"
    # Выключить можно и без Плюса.
    assert client.put("/api/notifications", headers=h, json={"email_enabled": False}).status_code == 200

    # Семье включили Плюс — напоминания пошли.
    client.put(f"/api/admin/families/{f}/plan", headers=h, json={"plan": "plus", "plus_until": None})
    client.put("/api/notifications", headers=h, json={"email_enabled": True})
    assert remind(db, u["id"]) == 1


# --- Telegram ---

def start_code(url: str) -> str:
    assert url.startswith("https://t.me/kapsulka_bot?start=")
    return url.rsplit("=", 1)[1]


def tg_message(text, chat_id=555, username="nikita"):
    return {"update_id": 1, "message": {"chat": {"id": chat_id, "type": "private"},
                                        "from": {"id": chat_id, "username": username}, "text": text}}


def test_telegram_link_flow(client, db, tg):
    h, u = register(client)
    assert client.put("/api/notifications", headers=h, json={"telegram_enabled": True}).status_code == 409
    r = client.post("/api/notifications/telegram/link", headers=h, json={"consent": True})
    assert r.status_code == 200
    code = start_code(r.json()["url"])

    answer = telegram.handle_update(db, tg_message(f"/start {code}"))
    assert "Готово, Никита" in answer
    p = client.get("/api/notifications", headers=h).json()
    assert p["telegram_connected"] and p["telegram_enabled"] and p["telegram_name"] == "@nikita"
    # Ссылка одноразовая.
    assert "не подошла" in telegram.handle_update(db, tg_message(f"/start {code}", chat_id=777))

    add(client, h, fid(u), "Нурофен", 3, min_quantity=5)
    assert remind(db, u["id"]) == 1
    method, params = tg[-1]
    assert method == "sendMessage" and params["chat_id"] == 555 and params["parse_mode"] == "HTML"
    assert "Нурофен: осталось 3 шт" in params["text"]

    # /stop в боте отвязывает.
    assert "отключён" in telegram.handle_update(db, tg_message("/stop"))
    assert client.get("/api/notifications", headers=h).json()["telegram_connected"] is False


def test_telegram_code_expires(client, db, tg):
    h, _ = register(client)
    code = start_code(client.post("/api/notifications/telegram/link", headers=h, json={"consent": True}).json()["url"])
    prefs = db.query(NotificationPrefs).one()
    prefs.telegram_code_sent_at = datetime.now() - timedelta(hours=2)
    db.commit()
    assert "не подошла" in telegram.handle_update(db, tg_message(f"/start {code}"))


def test_telegram_chat_moves_between_accounts(client, db, tg):
    h1, _ = register(client)
    h2, _ = register(client, "mom@example.com", "Мама")
    for h in (h1, h2):
        code = start_code(client.post("/api/notifications/telegram/link", headers=h, json={"consent": True}).json()["url"])
        telegram.handle_update(db, tg_message(f"/start {code}"))
    assert client.get("/api/notifications", headers=h1).json()["telegram_connected"] is False
    assert client.get("/api/notifications", headers=h2).json()["telegram_connected"] is True


def test_telegram_unlink_from_site(client, db, tg):
    h, _ = register(client)
    code = start_code(client.post("/api/notifications/telegram/link", headers=h, json={"consent": True}).json()["url"])
    telegram.handle_update(db, tg_message(f"/start {code}"))
    assert client.delete("/api/notifications/telegram", headers=h).status_code == 204
    assert client.get("/api/notifications", headers=h).json()["telegram_connected"] is False
    assert tg[-1][1]["chat_id"] == 555  # бот попрощался


def test_bot_ignores_groups_and_explains_itself(db, tg):
    group = tg_message("/start x")
    group["message"]["chat"]["type"] = "group"
    assert telegram.handle_update(db, group) is None
    assert "Капсулки" in telegram.handle_update(db, tg_message("привет"))


def test_telegram_needs_separate_consent(client, db, tg):
    h, _ = register(client)
    r = client.post("/api/notifications/telegram/link", headers=h, json={"consent": False})
    assert r.status_code == 422
    client.post("/api/notifications/telegram/link", headers=h, json={"consent": True})
    assert db.query(NotificationPrefs).one().telegram_consent_at is not None


def test_telegram_link_needs_bot(client):
    h, _ = register(client)
    assert client.post("/api/notifications/telegram/link", headers=h, json={"consent": True}).status_code == 409


def test_test_message(client, home, outbox, tg):
    h, _, _ = home
    assert client.post("/api/notifications/test", headers=h).status_code == 204
    assert "пробное" in text_of(outbox[-1])


def test_account_deletion_removes_settings(client, db, home):
    h, u, f = home
    add(client, h, f, "Нурофен", 3, min_quantity=5)
    remind(db, u["id"])
    r = client.request("DELETE", "/api/auth/me", headers=h, json={"password": "secret123"})
    assert r.status_code == 204
    db.expire_all()
    assert db.query(NotificationPrefs).count() == 0 and db.query(ReminderSent).count() == 0


# --- расписание ---

@pytest.mark.parametrize("hour, last, due", [
    (9, None, False),            # ещё рано
    (10, None, True),
    (15, "2026-09-30", True),    # вчерашняя была, сегодняшней нет (перезапуск после деплоя)
    (15, "2026-10-01", False),   # сегодня уже была
    (23, "2026-09-30", False),   # поздно: подождём утра
])
def test_daily_due(hour, last, due):
    now = datetime(2026, 10, 1, hour, 0, tzinfo=reminders.MSK)
    assert reminders.daily_due(now, last) is due


def test_nudge_without_background_thread_is_noop():
    reminders.nudge(1)
    assert reminders._queue.empty()


def test_fresh_package_window():
    class P:
        def __init__(self, added_at):
            self.added_at = added_at

    now = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)
    assert reminders._is_fresh(P(now - timedelta(hours=11, minutes=59)), now)
    assert not reminders._is_fresh(P(now - reminders.NEW_PACKAGE_DELAY), now)
    assert reminders._is_fresh(P(datetime(2026, 9, 30, 6)), now)  # без часового пояса = UTC


def test_debug_mode_skips_12h_delay(client, db, home, outbox):
    from app.services import set_debug_enabled
    h, u, f = home
    add(client, h, f, "Лоратадин", 4, expiry=TODAY - timedelta(days=3))
    now = datetime.now(timezone.utc)
    assert remind(db, u["id"], now=now) == 0
    set_debug_enabled(db, True)
    assert remind(db, u["id"], now=now) == 1
    assert "Лоратадин" in text_of(outbox[0])

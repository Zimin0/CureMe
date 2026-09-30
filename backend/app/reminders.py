"""Напоминания «скоро закончится» и «истекает срок» на почту и в Telegram (функция Плюса).

Что считается поводом напомнить:
- low — у лекарства задан порог «Напомнить, когда останется» (Medicine.min_quantity),
  и годный остаток стал не больше порога;
- expiring — у упаковки с остатком срок годности наступит через expiry_days дней или раньше;
- expired — у упаковки с остатком срок уже истёк.

Каждый повод человек получает один раз: отправленные лежат в reminders_sent. Когда повода
больше нет (остаток пополнили, упаковку выбросили), запись удаляется — и в следующий раз
напомним снова. Все новые поводы собираются в одно сообщение: одно письмо и одно сообщение
в Telegram в день, а не по штуке на лекарство. Про просрочку и скорый срок пишем только в
ежедневной сводке (после «Принял(а)» — лишь про остаток), а про упаковку, добавленную менее
12 часов назад, молчим до следующей сводки. В режиме отладки (админка) этих ограничений нет:
сообщение уходит сразу после добавления упаковки.

Когда проверяем:
- раз в день в CUREME_REMINDERS_HOUR по Москве — все семьи;
- сразу после «Принял(а)» — только эта семья: остаток мог только что опуститься до порога.

Планировщик — фоновый поток внутри приложения, а не cron или отдельный контейнер: на сервере
один процесс uvicorn, база и настройки уже под рукой, и нечего дополнительно разворачивать.
Если приложение перезапустили (деплой) и сегодняшняя рассылка ещё не прошла, она пройдёт
сразу после старта; повторов не будет благодаря reminders_sent.
"""

import logging
import queue
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html import escape

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from . import telegram
from .config import get_settings
from .email_verification import needs_verification
from .mailer import send_mail
from .models import AppSetting, Family, Medicine, Membership, NotificationPrefs, ReminderSent, User
from .plans import has_plus
from .services import debug_enabled, stock_of, telegram_active

log = logging.getLogger("cureme.reminders")
MSK = timezone(timedelta(hours=3))  # в Москве нет перехода на летнее время
LAST_RUN = "reminders_last_run"
NEW_PACKAGE_DELAY = timedelta(hours=12)  # про срок только что добавленной упаковки молчим первые 12 часов
QUIET_FROM = 22  # после 22:00 по Москве пропущенную ежедневную рассылку не догоняем, ждём утра


def plus_family_ids(db: Session, family_ids: list[int]) -> set[int]:
    """Семьи, у которых напоминания доступны: Плюс или платная версия выключена (plans.has_plus)."""
    return {f.id for f in db.scalars(select(Family).where(Family.id.in_(family_ids))) if has_plus(db, f)}


@dataclass(frozen=True)
class Reason:
    kind: str       # low | expiring | expired
    ref_id: int     # лекарство (low) или упаковка
    line: str       # строка для сообщения, уже без HTML
    sort: tuple


def _fmt_qty(x: float) -> str:
    return f"{x:g}".replace(".", ",")


def _days(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        word = "день"
    elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        word = "дня"
    else:
        word = "дней"
    return f"{n} {word}"


def _is_fresh(p, now: datetime) -> bool:
    added = p.added_at
    if added is None:
        return False
    if added.tzinfo is None:
        added = added.replace(tzinfo=timezone.utc)
    return now - added < NEW_PACKAGE_DELAY


def reasons_for(db: Session, user: User, prefs: NotificationPrefs, today: date,
                now: datetime | None = None) -> list[Reason]:
    """Все поводы напомнить этому человеку сейчас (и уже отправленные, и новые)."""
    fams = {m.family_id: m.family.name for m in db.scalars(
        select(Membership).where(Membership.user_id == user.id).options(selectinload(Membership.family)))}
    allowed = plus_family_ids(db, list(fams))
    if not allowed:
        return []
    many = len(fams) > 1
    meds = db.scalars(
        select(Medicine).where(Medicine.family_id.in_(allowed)).options(selectinload(Medicine.packages))
    ).all()
    now = now or datetime.now(timezone.utc)
    debug = debug_enabled(db)  # режим отладки: про новые упаковки сообщаем сразу
    out: list[Reason] = []
    for med in meds:
        where = f" ({fams[med.family_id]})" if many else ""
        stock = stock_of(med, today)
        if prefs.notify_low and med.min_quantity is not None and stock.total <= med.min_quantity:
            left = "закончилось" if stock.total <= 0 else f"осталось {_fmt_qty(stock.total)} {med.unit}"
            out.append(Reason("low", med.id, f"{med.name}{where}: {left}", (2, med.name)))
        if not prefs.notify_expiry:
            continue
        for p in med.packages:
            if p.quantity <= 0 or not p.expiry_date or (not debug and _is_fresh(p, now)):
                continue
            d = (p.expiry_date - today).days
            until = p.expiry_date.strftime("%d.%m.%Y")
            if d < 0:
                out.append(Reason("expired", p.id, f"{med.name}{where}: срок истёк {until}", (0, p.expiry_date, med.name)))
            elif d <= prefs.expiry_days:
                when = "сегодня последний день" if d == 0 else f"годен до {until}, осталось {_days(d)}"
                out.append(Reason("expiring", p.id, f"{med.name}{where}: {when}", (1, p.expiry_date, med.name)))
    return out


SECTIONS = [
    ("expired", "Срок годности истёк — лучше выбросить"),
    ("expiring", "Скоро истекает срок годности"),
    ("low", "Заканчиваются — пора купить"),
]


def compose(reasons: list[Reason]) -> tuple[str, str, str]:
    """(тема письма, текст письма, сообщение Telegram в HTML)."""
    site = get_settings().public_url or ""
    text_parts, html_parts = [], []
    for kind, title in SECTIONS:
        lines = sorted((r for r in reasons if r.kind == kind), key=lambda r: r.sort)
        if not lines:
            continue
        text_parts.append(title + ":\n" + "\n".join(f"• {r.line}" for r in lines))
        html_parts.append(f"<b>{escape(title)}</b>\n" + "\n".join(f"• {escape(r.line)}" for r in lines))
    kinds = {r.kind for r in reasons}
    subject = "Капсулка: " + (
        "лекарства заканчиваются" if kinds == {"low"} else "проверьте сроки годности" if "low" not in kinds
        else "лекарства требуют внимания"
    )
    footer = ("Открыть аптечку: " + site + "\n" if site else "") + \
        "Отключить напоминания: Капсулка → «Семья» → «Напоминания»."
    text = "Здравствуйте! Вот что в аптечке требует внимания.\n\n" + "\n\n".join(text_parts) + "\n\n" + footer
    html = "💊 <b>Капсулка</b>\n\n" + "\n\n".join(html_parts) + (f"\n\n{escape(site)}" if site else "")
    return subject, text, html


def can_email(user: User) -> bool:
    return bool(get_settings().smtp_host) and not needs_verification(user)


def deliver(user: User, prefs: NotificationPrefs, subject: str, text: str, html: str, tg_on: bool = False) -> bool:
    """Шлёт во все включённые каналы. True, если хотя бы один доставил."""
    ok = False
    if prefs.email_enabled and can_email(user):
        ok = send_mail(user.email, subject, text) or ok
    if prefs.telegram_enabled and prefs.telegram_chat_id and tg_on:
        ok = telegram.send_message(prefs.telegram_chat_id, html) or ok
    return ok


def has_channel(user: User, prefs: NotificationPrefs, tg_on: bool = False) -> bool:
    return (prefs.email_enabled and can_email(user)) or bool(
        prefs.telegram_enabled and prefs.telegram_chat_id and tg_on)


def remind_user(db: Session, user: User, today: date | None = None, kinds: set[str] | None = None,
                now: datetime | None = None) -> int:
    """Проверяет поводы одного человека и отправляет новые. Возвращает, сколько поводов отправлено."""
    prefs = db.get(NotificationPrefs, user.id)
    if not prefs or not has_channel(user, prefs, telegram_active(db)):
        return 0
    today = today or datetime.now(MSK).date()
    current = reasons_for(db, user, prefs, today, now)
    keys = {(r.kind, r.ref_id) for r in current}
    sent = {(s.kind, s.ref_id): s for s in db.scalars(select(ReminderSent).where(ReminderSent.user_id == user.id))}
    for key, row in sent.items():
        if key not in keys:  # повода больше нет — забываем, чтобы напомнить, если он вернётся
            db.delete(row)
    new = [r for r in current if (r.kind, r.ref_id) not in sent and (kinds is None or r.kind in kinds)]
    if new and deliver(user, prefs, *compose(new), tg_on=telegram_active(db)):
        db.add_all(ReminderSent(user_id=user.id, kind=r.kind, ref_id=r.ref_id) for r in new)
    else:
        new = []
    db.commit()
    return len(new)


def remind_users(db: Session, user_ids, kinds: set[str] | None = None) -> int:
    total = 0
    for uid in user_ids:
        user = db.get(User, uid)
        if not user:
            continue
        try:
            total += remind_user(db, user, kinds=kinds)
        except Exception:  # noqa: BLE001 — сбой у одного человека не должен остановить рассылку остальным
            log.exception("Напоминания для пользователя %s не отправлены", uid)
            db.rollback()
    return total


def run_daily(db: Session) -> int:
    ids = db.scalars(select(NotificationPrefs.user_id)).all()
    n = remind_users(db, ids)
    log.info("Ежедневные напоминания: %s человек с настройками, отправлено поводов: %s", len(ids), n)
    return n


def run_family(db: Session, family_id: int) -> int:
    ids = db.scalars(select(Membership.user_id).where(Membership.family_id == family_id)).all()
    # сроки годности — только в ежедневной сводке, а в режиме отладки сразу
    return remind_users(db, ids, kinds=None if debug_enabled(db) else {"low"})


# --- фоновый поток ---

_queue: "queue.Queue[int]" = queue.Queue(maxsize=1000)
_running = threading.Event()


def nudge(family_id: int) -> None:
    """Попросить проверить семью прямо сейчас (после «Принял(а)»). Без фонового потока — ничего не делает."""
    if _running.is_set():
        try:
            _queue.put_nowait(family_id)
        except queue.Full:
            pass


def _last_run(db: Session) -> str | None:
    row = db.get(AppSetting, LAST_RUN)
    return row.value if row else None


def _save_last_run(db: Session, day: str) -> None:
    row = db.get(AppSetting, LAST_RUN)
    if row:
        row.value = day
    else:
        db.add(AppSetting(key=LAST_RUN, value=day))
    db.commit()


def daily_due(now: datetime, last_run: str | None) -> bool:
    """Пора ли ежедневной рассылке: наступил её час, сегодня её ещё не было и ещё не поздний вечер."""
    return get_settings().reminders_hour <= now.hour < QUIET_FROM and last_run != now.date().isoformat()


def work_forever(session_factory, stop: threading.Event) -> None:
    _running.set()
    try:
        while not stop.is_set():
            now = datetime.now(MSK)
            with session_factory() as db:
                try:
                    if daily_due(now, _last_run(db)):
                        _save_last_run(db, now.date().isoformat())  # сначала отметка: сбой не зациклит рассылку
                        run_daily(db)
                except Exception:  # noqa: BLE001
                    log.exception("Ежедневные напоминания упали")
                    db.rollback()
            try:
                families = {_queue.get(timeout=60)}
            except queue.Empty:
                continue
            while not _queue.empty():
                families.add(_queue.get_nowait())
            with session_factory() as db:
                for fid in families:
                    if db.get(Family, fid):
                        run_family(db, fid)
    finally:
        _running.clear()


def start_background(session_factory) -> threading.Event:
    """Запускает фоновые потоки: напоминания и, если задан токен, Telegram-бота. Возвращает флаг остановки."""
    stop = threading.Event()
    threading.Thread(target=work_forever, args=(session_factory, stop), name="reminders", daemon=True).start()
    if get_settings().telegram_enabled:
        threading.Thread(target=telegram.poll_forever, args=(session_factory, stop), name="telegram", daemon=True).start()
    return stop

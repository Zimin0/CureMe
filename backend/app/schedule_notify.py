"""Уведомления о приёме по расписанию: себе на почту и доверенному человеку.

Для каждого приёма (см. schedule.py) по порядку:
1. pre      — за lead_minutes до времени приёма письмо себе: «скоро пора принять»;
2. repeat   — через repeat_minutes после времени приёма, если в истории приёма отметки нет, письмо себе ещё раз;
3. trusted  — ещё через escalate_minutes, если отметки всё нет, письмо доверенному человеку.
Если отметка появилась (в том числе раньше времени приёма), следующие письма по этому приёму не уходят.

Письма доверенному уходят только после его согласия (TrustedContact.status == confirmed) и по умолчанию
не называют лекарство: «не отмечен плановый приём», а не «не выпил(а) такое-то лекарство».

Каждое уведомление отправляется один раз: отправленные лежат в schedule_notified. Если письмо не ушло
(сбой почты), пробуем снова каждую минуту, но только в течение GRACE после нужного момента:
запоздалое напоминание хуже, чем никакого. Функция доступна с Плюсом, как остальные напоминания.
"""

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .mailer import send_mail
from .models import Membership, ScheduleNotified, SchedulePrefs, TrustedContact, User, utcnow
from .reminders import MSK, can_email, plus_family_ids
from .schedule import Occurrence, occurrences
from .services import _aware

log = logging.getLogger("cureme.schedule")
GRACE = timedelta(minutes=30)       # сколько после нужного момента ещё пытаемся отправить
TRUSTED_PER_DAY = 12                # писем доверенному человеку в сутки, чтобы не заспамить его при сбое
INVITE_TTL = timedelta(days=30)        # неотвеченное приглашение через месяц удаляется вместе с почтой
OPERATOR_LINE = "Оператор: Зименков Никита Вячеславович, вопросы: work_notifications_zimino@mail.ru"
CONSENT_VERSION = "trusted-2026-09-30.1"  # редакция текста согласия на странице доверенного (TrustedConsent.tsx)
STAGES = ("pre", "repeat", "trusted")


def _site() -> str:
    return (get_settings().public_url or "").rstrip("/")


def _at(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def _qty(x: float) -> str:
    return f"{x:g}".replace(".", ",")


def _minutes(n: int) -> str:
    word = "минуту" if n % 10 == 1 and n % 100 != 11 else "минуты" if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else "минут"
    return f"{n} {word}"


# --- письма ---
def _lines(items: list[Occurrence]) -> str:
    return "\n".join(f"• {_at(o.minute)} — {o.schedule.medicine_name}, {_qty(o.schedule.amount)} {o.schedule.unit}" for o in items)


def send_self(user: User, stage: str, items: list[Occurrence], lead: int) -> bool:
    site = _site()
    if stage == "pre":
        subject = "Капсулка: скоро приём лекарства"
        head = f"Через {_minutes(lead)} по расписанию:"
        tail = "Когда примете, нажмите «Принял(а)» на вкладке «Расписание»: отметка попадёт в историю приёма."
    else:
        subject = "Капсулка: вы не отметили приём"
        head = "Время приёма прошло, а отметки в истории приёма нет:"
        tail = ("Если уже приняли, нажмите «Принял(а)» на вкладке «Расписание». Если нет, самое время: "
                "иначе мы сообщим доверенному человеку, если вы его указали.")
    text = f"Здравствуйте, {user.name}!\n\n{head}\n{_lines(items)}\n\n{tail}" + (f"\n\n{site}/schedule" if site else "")
    text += "\n\nУведомления можно отключить на вкладке «Расписание»."
    return send_mail(user.email, subject, text)


def token_for(contact: TrustedContact) -> str:
    """Ссылка доверенного не хранится в базе: «id.подпись». Подделать без секретного ключа сайта нельзя."""
    sig = hmac.new(get_settings().secret_key.encode(), f"trusted:{contact.id}:{contact.nonce}".encode(), hashlib.sha256).hexdigest()
    return f"{contact.id}.{sig[:40]}"


def contact_by_token(db: Session, token: str) -> TrustedContact | None:
    head, _, _ = token.partition(".")
    contact = db.get(TrustedContact, int(head)) if head.isdigit() else None
    return contact if contact and hmac.compare_digest(token_for(contact), token) else None


def new_nonce() -> str:
    return secrets.token_hex(8)


def trusted_link(contact: TrustedContact) -> str:
    # Токен после «#»: эту часть адреса браузер не отправляет на сервер, и она не попадает в логи Caddy.
    return f"{_site()}/trusted#{token_for(contact)}"


def send_trusted_request(contact: TrustedContact, user_name: str) -> bool:
    text = (
        f"Здравствуйте, {contact.name}!\n\n"
        f"{user_name} пользуется Капсулкой — домашней аптечкой — и указал(а) вас доверенным человеком: "
        f"если {user_name} не отметит плановый приём лекарства, мы пришлём вам короткое письмо, "
        "чтобы вы могли связаться. Название лекарства в письме по умолчанию не указывается.\n\n"
        "Мы написали вам только потому, что нас об этом попросил пользователь. Пока вы не согласитесь, "
        "никаких уведомлений вам не придёт. Согласиться, отказаться или позже отписаться можно по ссылке:\n"
        f"{trusted_link(contact)}\n\n"
        "Если вы не знаете, кто это, просто проигнорируйте письмо или откажитесь по ссылке: больше мы вам не напишем. "
        "Если вы не ответите, через 30 дней мы удалим ваши имя и почту.\n\n"
        f"{OPERATOR_LINE}, подробнее: {_site()}/consent-trusted"
    )
    return send_mail(contact.email, "Капсулка: вас просят быть доверенным человеком", text)


def send_trusted_alert(contact: TrustedContact, user: User, items: list[Occurrence], share_names: bool) -> bool:
    times = ", ".join(sorted({_at(o.minute) for o in items}))
    what = ("Лекарство: " + ", ".join(sorted({o.schedule.medicine_name for o in items})) + f"\nВремя приёма по расписанию: {times}"
            if share_names else f"Время планового приёма: {times}")
    text = (
        f"Здравствуйте, {contact.name}!\n\n"
        f"{user.name} не отметил(а) плановый приём лекарства в Капсулке, хотя прошло время напоминаний.\n{what}\n\n"
        f"Возможно, стоит связаться с {user.name} и узнать, всё ли в порядке. Это автоматическое письмо: "
        "оно не означает, что что-то случилось, и не заменяет помощь врача.\n\n"
        f"Вы получаете такие письма, потому что согласились на это. Отписаться: {trusted_link(contact)}"
    )
    return send_mail(contact.email, f"Капсулка: {user.name} не отметил(а) приём", text)


# --- ядро ---
@dataclass
class Due:
    occ: Occurrence
    stage: str


def due_items(prefs: SchedulePrefs, occs: list[Occurrence], now: datetime, trusted_ok: bool) -> list[Due]:
    """Какие уведомления пора отправить прямо сейчас (без учёта уже отправленных)."""
    out: list[Due] = []
    for o in occs:
        if o.taken_at is not None:
            continue
        moments = {
            "pre": (o.due - timedelta(minutes=prefs.lead_minutes), o.due),
            "repeat": (o.due + timedelta(minutes=prefs.repeat_minutes), None),
            "trusted": (o.due + timedelta(minutes=prefs.repeat_minutes + prefs.escalate_minutes), None),
        }
        for stage, (start, stop) in moments.items():
            if stage == "trusted" and not (trusted_ok and prefs.escalate_enabled and prefs.escalate_consent_at):
                continue
            end = stop or start + GRACE
            if start <= now < min(end, start + GRACE):
                out.append(Due(o, stage))
    return out


def notify_user(db: Session, user: User, prefs: SchedulePrefs, now: datetime) -> int:
    """Проверяет приёмы одного человека и отправляет нужные уведомления. Возвращает, сколько отправлено."""
    if not prefs.enabled or not can_email(user):
        return 0
    fams = list(db.scalars(select(Membership.family_id).where(Membership.user_id == user.id)))
    if not plus_family_ids(db, fams):
        return 0
    today = now.astimezone(MSK).date()
    occs = occurrences(db, user.id, today - timedelta(days=1), today + timedelta(days=1))
    if not occs:
        return 0
    contact = db.scalar(select(TrustedContact).where(TrustedContact.user_id == user.id))
    trusted_ok = bool(contact and contact.status == "confirmed")
    sent = {(n.slot_id, n.day, n.stage) for n in db.scalars(
        select(ScheduleNotified).where(ScheduleNotified.user_id == user.id, ScheduleNotified.day >= today - timedelta(days=1)))}
    todo = [d for d in due_items(prefs, occs, now, trusted_ok) if (d.occ.slot_id, d.occ.day, d.stage) not in sent]
    count = 0
    for stage in STAGES:
        group = [d.occ for d in todo if d.stage == stage]
        if not group:
            continue
        if stage == "trusted":
            day_ago = utcnow() - timedelta(days=1)
            done = db.scalar(select(func.count()).select_from(ScheduleNotified).where(
                ScheduleNotified.user_id == user.id, ScheduleNotified.stage == "trusted", ScheduleNotified.sent_at >= day_ago)) or 0
            if done >= TRUSTED_PER_DAY:
                log.warning("Доверенному человеку пользователя %s за сутки уже %s писем, новые не отправляем", user.id, done)
                continue
            ok = send_trusted_alert(contact, user, group, prefs.share_medicine_name)
        else:
            ok = send_self(user, stage, group, prefs.lead_minutes)
        if ok:
            db.add_all(ScheduleNotified(user_id=user.id, slot_id=o.slot_id, day=o.day, stage=stage) for o in group)
            count += 1
        db.commit()
    return count


def purge_stale_invites(db: Session, now: datetime) -> int:
    """Приглашения без ответа старше 30 дней удаляются вместе с именем и почтой человека."""
    cutoff = now - INVITE_TTL
    stale = [c for c in db.scalars(select(TrustedContact).where(TrustedContact.status == "pending"))
             if _aware(c.request_sent_at or c.created_at) < cutoff]
    for c in stale:
        db.delete(c)
    if stale:
        db.commit()
    return len(stale)


def run_due(db: Session, now: datetime | None = None) -> int:
    """Раз в минуту из фонового потока: все, у кого включены уведомления по расписанию."""
    now = now or datetime.now(timezone.utc)
    purge_stale_invites(db, now)
    total = 0
    for prefs in db.scalars(select(SchedulePrefs).where(SchedulePrefs.enabled.is_(True))).all():
        user = db.get(User, prefs.user_id)
        if not user:
            continue
        try:
            total += notify_user(db, user, prefs, now)
        except Exception:  # noqa: BLE001 — сбой у одного человека не должен остановить остальных
            log.exception("Уведомления по расписанию для пользователя %s не отправлены", prefs.user_id)
            db.rollback()
    return total

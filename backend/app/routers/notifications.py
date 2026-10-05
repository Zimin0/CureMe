from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import telegram
from ..config import get_settings
from ..db import get_db
from ..deps import current_user
from ..mailer import send_mail
from ..models import Membership, NotificationPrefs, User, utcnow
from ..plans import plus_required
from ..ratelimit import limiter
from ..reminders import can_email, nudge_user, plus_family_ids
from ..services import telegram_active
from ..schemas import NotificationPrefsIn, NotificationPrefsOut, TelegramLinkIn, TelegramLinkOut

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _prefs(db: Session, user: User) -> NotificationPrefs:
    prefs = db.get(NotificationPrefs, user.id)
    if not prefs:
        prefs = NotificationPrefs(user_id=user.id, email_enabled=False, telegram_enabled=False,
                                  notify_low=True, notify_expiry=True, notify_expired=True,
                                  expiry_days=get_settings().expiring_soon_days)
        db.add(prefs)
        db.flush()
    return prefs


def _require_telegram(db: Session) -> None:
    """Админ спрятал Telegram: для API такой функции как будто нет."""
    if not telegram_active(db):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")


def _available(db: Session, user: User) -> bool:
    fams = db.scalars(select(Membership.family_id).where(Membership.user_id == user.id)).all()
    return bool(plus_family_ids(db, list(fams)))


def _out(db: Session, user: User, prefs: NotificationPrefs | None) -> NotificationPrefsOut:
    s = get_settings()
    tg = telegram_active(db)
    return NotificationPrefsOut(
        available=_available(db, user),
        email=user.email,
        email_possible=can_email(user),
        telegram_possible=tg,
        telegram_bot=s.telegram_bot_username if tg else None,
        email_enabled=bool(prefs and prefs.email_enabled),
        telegram_enabled=bool(tg and prefs and prefs.telegram_enabled and prefs.telegram_chat_id),
        telegram_connected=bool(tg and prefs and prefs.telegram_chat_id),
        telegram_name=prefs.telegram_name if tg and prefs else None,
        notify_low=prefs.notify_low if prefs else True,
        notify_expiry=prefs.notify_expiry if prefs else True,
        notify_expired=prefs.notify_expired if prefs else True,
        expiry_days=prefs.expiry_days if prefs else s.expiring_soon_days,
    )


def _require_plus(db: Session, user: User) -> None:
    if not _available(db, user):
        raise plus_required("reminders")


@router.get("", response_model=NotificationPrefsOut)
def get_prefs(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _out(db, user, db.get(NotificationPrefs, user.id))


@router.put("", response_model=NotificationPrefsOut)
def update_prefs(body: NotificationPrefsIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    prefs = _prefs(db, user)
    data = body.model_dump(exclude_unset=True)
    if "telegram_enabled" in data:
        _require_telegram(db)
    turning_on = data.get("email_enabled") or data.get("telegram_enabled")
    if turning_on:
        _require_plus(db, user)
    if data.get("email_enabled") and not can_email(user):
        raise HTTPException(status.HTTP_409_CONFLICT, "Отправка писем на сайте пока не настроена")
    if data.get("telegram_enabled") and not prefs.telegram_chat_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Сначала подключите Telegram")
    for k, v in data.items():
        setattr(prefs, k, v)
    db.commit()
    if data and (prefs.email_enabled or prefs.telegram_enabled):
        nudge_user(user.id)  # новые настройки действуют сразу, а не со следующей сводки
    return _out(db, user, prefs)


@router.post("/telegram/link", response_model=TelegramLinkOut)
def telegram_link(body: TelegramLinkIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Одноразовая ссылка на бота: открыв её, человек привязывает свой Telegram к аккаунту.

    Сначала — отдельное согласие на трансграничную передачу (страница /consent-telegram):
    напоминания с названиями лекарств пойдут через серверы Telegram за рубежом.
    """
    _require_telegram(db)
    if not body.consent:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Нужно согласие на передачу данных в Telegram")
    _require_plus(db, user)
    limiter.hit(f"tg-link:{user.id}", limit=10, window=3600)
    prefs = _prefs(db, user)
    prefs.telegram_consent_at = utcnow()
    url = telegram.link_url(prefs)
    db.commit()
    return TelegramLinkOut(url=url, ttl_minutes=get_settings().telegram_link_ttl_minutes)


@router.delete("/telegram", status_code=204)
def telegram_unlink(background: BackgroundTasks, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _require_telegram(db)
    prefs = db.get(NotificationPrefs, user.id)
    if prefs and prefs.telegram_chat_id:
        chat_id = prefs.telegram_chat_id
        prefs.telegram_chat_id = prefs.telegram_name = None
        prefs.telegram_enabled = False
        db.commit()
        background.add_task(telegram.send_message, chat_id, "Telegram отключён от Капсулки, напоминаний сюда больше не будет.")
    return Response(status_code=204)


@router.post("/test", status_code=204)
def send_test(background: BackgroundTasks, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Пробное напоминание во все включённые каналы: убедиться, что всё доходит."""
    prefs = db.get(NotificationPrefs, user.id)
    email = bool(prefs and prefs.email_enabled and can_email(user))
    tg = bool(prefs and prefs.telegram_enabled and prefs.telegram_chat_id and telegram_active(db))
    if not (email or tg):
        raise HTTPException(status.HTTP_409_CONFLICT, "Включите почту или Telegram")
    limiter.hit(f"notify-test:{user.id}", limit=3, window=600)
    text = "Это пробное напоминание Капсулки. Если вы его видите — напоминания будут приходить сюда."
    if email:
        background.add_task(send_mail, user.email, "Капсулка: пробное напоминание", text)
    if tg:
        background.add_task(telegram.send_message, prefs.telegram_chat_id, text)
    return Response(status_code=204)

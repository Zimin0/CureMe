"""Настройки уведомлений по расписанию (себе на почту, доверенному человеку) и страница доверенного по ссылке из письма."""

from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import Membership, SchedulePrefs, TrustedContact, User, utcnow
from ..plans import plus_required
from ..ratelimit import client_ip, limiter
from ..reminders import can_email, plus_family_ids
from ..schedule_notify import CONSENT_VERSION, SHARE_CONSENT_VERSION, contact_by_token, new_nonce, send_trusted_request
from ..schemas import SchedulePrefsIn, SchedulePrefsOut, TrustedIn, TrustedOut, TrustedPublicOut, TrustedTokenIn

router = APIRouter(prefix="/api/schedule-notifications", tags=["schedule-notifications"])
public = APIRouter(prefix="/api/trusted", tags=["trusted"])


def _prefs(db: Session, user: User) -> SchedulePrefs:
    prefs = db.get(SchedulePrefs, user.id)
    if not prefs:
        prefs = SchedulePrefs(user_id=user.id, enabled=False, lead_minutes=10, repeat_minutes=10,
                              escalate_enabled=False, escalate_minutes=10, share_medicine_name=False)
        db.add(prefs)
        db.flush()
    return prefs


def _available(db: Session, user: User) -> bool:
    fams = db.scalars(select(Membership.family_id).where(Membership.user_id == user.id)).all()
    return bool(plus_family_ids(db, list(fams)))


def _require_plus(db: Session, user: User) -> None:
    if not _available(db, user):
        raise plus_required("reminders")


def _out(db: Session, user: User) -> SchedulePrefsOut:
    prefs = db.get(SchedulePrefs, user.id)
    c = db.scalar(select(TrustedContact).where(TrustedContact.user_id == user.id))
    return SchedulePrefsOut(
        available=_available(db, user), email=user.email, email_possible=can_email(user),
        enabled=bool(prefs and prefs.enabled), lead_minutes=prefs.lead_minutes if prefs else 10,
        repeat_minutes=prefs.repeat_minutes if prefs else 10,
        escalate_enabled=bool(prefs and prefs.escalate_enabled), escalate_minutes=prefs.escalate_minutes if prefs else 10,
        share_medicine_name=bool(prefs and prefs.share_medicine_name),
        escalate_consent_at=prefs.escalate_consent_at if prefs else None,
        escalate_consent_version=prefs.escalate_consent_version if prefs else None,
        trusted=TrustedOut(name=c.name, email=c.email, status=c.status, confirmed_at=c.confirmed_at) if c else None,
    )


@router.get("", response_model=SchedulePrefsOut)
def get_prefs(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _out(db, user)


@router.put("", response_model=SchedulePrefsOut)
def update_prefs(body: SchedulePrefsIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)
    consent = data.pop("escalate_consent", None)
    if data.get("enabled") or data.get("escalate_enabled"):
        _require_plus(db, user)
    if data.get("escalate_enabled"):
        # Письмо доверенному раскрывает сведения о здоровье: нужно отдельное разрешение пользователя, с датой.
        if not consent:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "Отметьте, что разрешаете сообщать доверенному человеку о неотмеченном приёме")
        data["escalate_consent_at"], data["escalate_consent_version"] = utcnow(), SHARE_CONSENT_VERSION
    elif data.get("escalate_enabled") is False:
        data["escalate_consent_at"] = data["escalate_consent_version"] = None  # выключили — разрешение снято, при новом включении спросим снова
    if data.get("enabled") and not can_email(user):
        raise HTTPException(status.HTTP_409_CONFLICT, "Отправка писем на сайте пока не настроена")
    prefs = _prefs(db, user)
    for k, v in data.items():
        setattr(prefs, k, v)
    db.commit()
    return _out(db, user)


@router.post("/trusted", response_model=SchedulePrefsOut)
def set_trusted(
    body: TrustedIn, background: BackgroundTasks, user: User = Depends(current_user), db: Session = Depends(get_db),
):
    """Указать доверенного человека: ему уходит письмо с просьбой согласиться, уведомления — только после согласия."""
    _require_plus(db, user)
    if not body.attest:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Подтвердите, что этот человек согласен получать письма")
    email = str(body.email).strip().lower()
    if email == user.email.lower():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Это ваша собственная почта: укажите другого человека")
    if not can_email(user):
        raise HTTPException(status.HTTP_409_CONFLICT, "Отправка писем на сайте пока не настроена")
    c = db.scalar(select(TrustedContact).where(TrustedContact.user_id == user.id))
    if c and c.email.lower() == email and c.status in ("pending", "confirmed"):
        c.name = body.name  # та же почта: имя можно поправить, письмо не шлём, согласие сохраняется
        db.commit()
        return _out(db, user)
    # Защита от рассылки чужим людям: мало запросов с аккаунта и мало писем на один адрес с любых аккаунтов.
    limiter.hit(f"trusted-user:{user.id}", limit=5, window=86400)
    limiter.hit(f"trusted-addr:{email}", limit=2, window=86400)
    if c:
        db.delete(c)  # другая почта (или человек отказался): начинаем заново, старые ссылки перестают работать
        db.flush()
    c = TrustedContact(user_id=user.id, name=body.name, email=email, status="pending", nonce=new_nonce(),
                       request_sent_at=utcnow())
    db.add(c)
    db.commit()
    background.add_task(send_trusted_request, c, user.name)
    return _out(db, user)


@router.post("/trusted/resend", response_model=SchedulePrefsOut)
def resend_trusted(background: BackgroundTasks, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = db.scalar(select(TrustedContact).where(TrustedContact.user_id == user.id))
    if not c or c.status != "pending":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Нечего отправлять: доверенный человек не ждёт ответа")
    limiter.hit(f"trusted-user:{user.id}", limit=5, window=86400)
    limiter.hit(f"trusted-addr:{c.email.lower()}", limit=2, window=86400)
    c.request_sent_at = utcnow()
    db.commit()
    background.add_task(send_trusted_request, c, user.name)
    return _out(db, user)


@router.delete("/trusted", status_code=204)
def remove_trusted(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Убрать доверенного человека: его почта и имя удаляются, ссылки из писем перестают работать."""
    c = db.scalar(select(TrustedContact).where(TrustedContact.user_id == user.id))
    if c:
        db.delete(c)
    prefs = db.get(SchedulePrefs, user.id)
    if prefs:
        prefs.escalate_enabled = False
        prefs.escalate_consent_at = prefs.escalate_consent_version = None  # доверенного нет — разрешение снято
    db.commit()
    return Response(status_code=204)


# --- страница доверенного человека: без входа, по ссылке из письма ---
def _contact(db: Session, request: Request, body: TrustedTokenIn) -> TrustedContact:
    limiter.hit(f"trusted-token:{client_ip(request)}", limit=30, window=600)
    c = contact_by_token(db, body.token)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ссылка недействительна: возможно, человек, который вас указал, её отозвал")
    return c


@public.post("/lookup", response_model=TrustedPublicOut)
def lookup(body: TrustedTokenIn, request: Request, db: Session = Depends(get_db)):
    c = _contact(db, request, body)
    return TrustedPublicOut(user_name=db.get(User, c.user_id).name, status=c.status)


def _set_status(db: Session, c: TrustedContact, new: str) -> TrustedPublicOut:
    c.status = new
    if new == "confirmed":
        c.confirmed_at, c.consent_version = utcnow(), CONSENT_VERSION
    else:
        c.name = c.email = ""  # отказался или отписался: имя и почту стираем, остаётся только статус
        c.confirmed_at = None
    db.commit()
    return TrustedPublicOut(user_name=db.get(User, c.user_id).name, status=c.status)


@public.post("/confirm", response_model=TrustedPublicOut)
def confirm(body: TrustedTokenIn, request: Request, db: Session = Depends(get_db)):
    c = _contact(db, request, body)
    if c.status in ("declined", "revoked"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Вы уже отказались. Если передумали, попросите человека отправить приглашение снова")
    return _set_status(db, c, "confirmed")


@public.post("/decline", response_model=TrustedPublicOut)
def decline(body: TrustedTokenIn, request: Request, db: Session = Depends(get_db)):
    c = _contact(db, request, body)
    if c.status in ("declined", "revoked"):
        return TrustedPublicOut(user_name=db.get(User, c.user_id).name, status=c.status)
    return _set_status(db, c, "declined" if c.status == "pending" else "revoked")

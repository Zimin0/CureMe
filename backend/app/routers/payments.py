"""Оплата Плюса: создание платежа, уведомления ЮKassa, автопродление. Логика — в payments.py."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import households, payments
from ..db import get_db
from ..deps import current_user
from ..models import Payment, User
from ..plans import PLUS, plus_active
from ..schemas import PayIn, PayStarted, PayStatus, PaymentBrief

router = APIRouter(prefix="/api/payments", tags=["payments"])


def _status(db: Session, user: User) -> PayStatus:
    rows = db.scalars(select(Payment).where(Payment.user_id == user.id).order_by(Payment.id.desc()).limit(10))
    house = user.household
    owner = households.owner_of(house)
    is_owner = owner is not None and owner.id == user.id
    enabled = payments.payments_enabled(db)
    lifetime = house is not None and house.plan == PLUS and house.plus_until is None  # Плюс без срока от администратора
    return PayStatus(
        enabled=enabled, plus_active=plus_active(user),
        plus_until=house.plus_until if house else None,
        # Платит и продлевает только владелец (R06): остальным кнопки оплаты нет, вместо неё имя владельца.
        is_owner=is_owner, owner_name=owner.name if owner else None, can_pay=enabled and is_owner and not lifetime,
        auto_renew=user.auto_renew and is_owner, recurring_enabled=payments.recurring_enabled(),
        price_month=payments.price_for(db, "month"), price_year=payments.price_for(db, "year"),
        payments=[PaymentBrief.model_validate(p, from_attributes=True) for p in rows],
    )


@router.get("/me", response_model=PayStatus)
def my_payments(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _status(db, user)


@router.post("", response_model=PayStarted, status_code=201)
def start(body: PayIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not payments.payments_enabled(db):
        raise HTTPException(409, "Оплата пока недоступна")
    if body.auto_renew and not payments.recurring_enabled():
        raise HTTPException(409, "Автопродление пока недоступно")
    try:
        pay, url = payments.create_payment(db, user, body.period, body.auto_renew)
    except payments.PaymentError as e:
        raise HTTPException(502, str(e)) from e
    return PayStarted(payment_id=pay.id, confirmation_url=url)


@router.post("/auto-renew/off", response_model=PayStatus)
def auto_renew_off(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Кнопка «Отключить автопродление»: забываем способ оплаты, больше ничего не спишется."""
    user.auto_renew = False
    user.pay_method_id = None
    user.renew_notified_for = None
    db.commit()
    return _status(db, user)


@router.post("/yookassa/webhook", include_in_schema=False)
async def webhook(request: Request, db: Session = Depends(get_db)):
    """HTTP-уведомление ЮKassa. Телу не верим: берём id и сами спрашиваем платёж у ЮKassa."""
    if not payments.configured():
        raise HTTPException(404)
    try:
        body = await request.json()
        obj = body["object"]
        yk_id = obj["payment_id"] if str(body.get("event", "")).startswith("refund.") else obj["id"]
    except (ValueError, KeyError, TypeError):
        raise HTTPException(400, "Неверное уведомление")
    try:
        payments.sync_payment(db, str(yk_id))
    except payments.PaymentError as e:
        raise HTTPException(503, "Повторите позже") from e  # ЮKassa пришлёт уведомление ещё раз
    return {"ok": True}

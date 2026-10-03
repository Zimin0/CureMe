"""Панель администратора: все аккаунты, все семьи и общий список категорий."""
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .. import household_check
from ..config import get_settings
from ..db import get_db
from ..deps import admin_user
from ..mailer import send_mail
from ..models import Category, Family, Medicine, MedicineCategory, Membership, Payment, User
from ..schemas import (
    AccessSettings, AdminPaymentOut, AdminPlanIn, ReceiptIn, BillingSettings, DebugSettings, TelegramSettings,
    AdminFamilyOut, AdminMemberIn, AdminStats, AdminUserOut, AdminUserUpdate, CategoryIn, CategoryOrderIn,
    CategoryOut, FamilyBrief, FamilyIn, IndicationHintsIn, MemberOut, RoleIn,
)
from ..email_verification import mark_verified
from ..plans import billing_settings, family_owner_user, plus_active, set_billing_settings
from ..security import hash_password
from ..services import access_settings, debug_enabled, indication_hints, set_access_settings, set_debug_enabled, set_indication_hints, set_telegram_switch, telegram_switch_on
from .files import _drop_photo

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(admin_user)])


def _not_found(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} не найден")


def _get_user(db: Session, user_id: int) -> User:
    u = db.get(User, user_id)
    if not u:
        raise _not_found("Пользователь")
    return u


def _user_out(u: User) -> AdminUserOut:
    fams = sorted(u.memberships, key=lambda m: m.joined_at)
    return AdminUserOut(
        id=u.id, email=u.email, name=u.name, is_admin=u.is_admin, email_verified=u.email_verified_at is not None,
        created_at=u.created_at,
        families=[FamilyBrief(id=m.family_id, name=m.family.name, role=m.role) for m in fams],
        plan=u.plan, plus_until=u.plus_until, plus_active=plus_active(u), auto_renew=u.auto_renew,
        plus_from_others=_plus_from_others(u),
    )


def _plus_from_others(u: User) -> list[str]:
    """Аптечки, где человек не главный владелец, но Плюс есть: он идёт от тарифа главного владельца, а не от тарифа человека."""
    out = []
    for m in sorted(u.memberships, key=lambda m: m.joined_at):
        owner = family_owner_user(m.family)
        if owner and owner.id != u.id and plus_active(owner):
            out.append(f"{m.family.name} (Плюс у {owner.name})")
    return out


def _family_out(db: Session, f: Family) -> AdminFamilyOut:
    count = db.scalar(select(func.count()).select_from(Medicine).where(Medicine.family_id == f.id)) or 0
    members = sorted(f.memberships, key=lambda m: (m.role != "owner", m.joined_at))
    owner = family_owner_user(f)
    return AdminFamilyOut(
        id=f.id, name=f.name, invite_code=f.invite_code, created_at=f.created_at, medicine_count=count,
        members=[
            MemberOut(user_id=m.user_id, name=m.user.name, email=m.user.email, role=m.role, joined_at=m.joined_at)
            for m in members
        ],
        plan=owner.plan if owner else "free", plus_until=owner.plus_until if owner else None,
        plus_active=plus_active(owner), owner_id=owner.id if owner else None, owner_name=owner.name if owner else None,
    )


def _delete_family(db: Session, f: Family) -> None:
    for name in db.scalars(select(Medicine.photo).where(Medicine.family_id == f.id, Medicine.photo.is_not(None))):
        _drop_photo(name)
    db.delete(f)


def _leave(db: Session, m: Membership) -> None:
    """Убирает человека из семьи так, чтобы у семьи остался владелец, а пустая семья исчезла."""
    others = sorted((x for x in m.family.memberships if x.id != m.id), key=lambda x: x.joined_at)
    if not others:
        _delete_family(db, m.family)
        return
    if m.role == "owner" and not any(x.role == "owner" for x in others):
        others[0].role = "owner"
    db.delete(m)


@router.get("/stats", response_model=AdminStats)
def stats(db: Session = Depends(get_db)):
    count = lambda model, *where: db.scalar(select(func.count()).select_from(model).where(*where)) or 0  # noqa: E731
    return AdminStats(
        users=count(User), admins=count(User, User.is_admin.is_(True)), families=count(Family),
        medicines=count(Medicine), categories=count(Category),
    )


# --- пользователи ---
@router.get("/household-check")
def household_check_report(db: Session = Depends(get_db)):
    """Только чтение: можно ли без потерь склеить текущие аптечки в семьи (docs/household-model, PR 3)."""
    return household_check.analyze(db)


@router.get("/users", response_model=list[AdminUserOut])
def list_users(db: Session = Depends(get_db)):
    users = db.scalars(
        select(User).options(selectinload(User.memberships).selectinload(Membership.family)).order_by(User.created_at)
    )
    return [_user_out(u) for u in users]


@router.put("/users/{user_id}/plan", response_model=AdminUserOut)
def set_user_plan(user_id: int, body: AdminPlanIn, db: Session = Depends(get_db)):
    """Ручное включение Плюса аккаунту (оплаты пока нет). Плюс действует на все аптечки, где он главный владелец.
    Бесплатный тариф сбрасывает срок и автопродление: сохранённый способ оплаты забываем, иначе человек остался бы
    с включённым автопродлением и кнопкой «Отключить» у тарифа, которого у него уже нет."""
    u = _get_user(db, user_id)
    u.plan = body.plan
    u.plus_until = body.plus_until if body.plan == "plus" else None
    if body.plan != "plus":
        u.auto_renew, u.pay_method_id, u.renew_period, u.renew_notified_for, u.renew_notified_at = False, None, None, None, None
    db.commit()
    return _user_out(u)


@router.patch("/users/{user_id}", response_model=AdminUserOut)
def update_user(user_id: int, body: AdminUserUpdate, me: User = Depends(admin_user), db: Session = Depends(get_db)):
    u = _get_user(db, user_id)
    if body.is_admin is False and u.id == me.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Нельзя снять права администратора с самого себя")
    if body.email and body.email.lower() != u.email:
        if db.scalar(select(User.id).where(func.lower(User.email) == body.email.lower(), User.id != u.id)):
            raise HTTPException(status.HTTP_409_CONFLICT, "Аккаунт с такой почтой уже есть")
        u.email = body.email.lower()
        mark_verified(u)  # почту вписал администратор — он за неё и ручается
    if body.email_verified is not None and body.email_verified != (u.email_verified_at is not None):
        if body.email_verified:
            mark_verified(u)
        else:
            u.email_verified_at = None
    if body.name:
        u.name = body.name.strip()
    if body.is_admin is not None:
        u.is_admin = body.is_admin
    if body.password:
        u.password_hash = hash_password(body.password)
        u.token_version += 1  # человека выкинет со всех устройств: войти можно только с новым паролем
    db.commit()
    return _user_out(u)


@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int, me: User = Depends(admin_user), db: Session = Depends(get_db)):
    u = _get_user(db, user_id)
    if u.id == me.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Нельзя удалить свой собственный аккаунт")
    for m in list(u.memberships):
        _leave(db, m)
    db.flush()
    db.expire(u, ["memberships"])  # часть членств уже удалилась вместе с опустевшими семьями
    db.delete(u)
    db.commit()
    return Response(status_code=204)


# --- семьи ---
def _family(db: Session, family_id: int) -> Family:
    f = db.get(Family, family_id)
    if not f:
        raise HTTPException(404, "Семья не найдена")
    return f


@router.get("/families", response_model=list[AdminFamilyOut])
def list_families(db: Session = Depends(get_db)):
    fams = db.scalars(
        select(Family).options(selectinload(Family.memberships).selectinload(Membership.user)).order_by(Family.created_at)
    )
    return [_family_out(db, f) for f in fams]


@router.patch("/families/{family_id}", response_model=AdminFamilyOut)
def rename_family(family_id: int, body: FamilyIn, db: Session = Depends(get_db)):
    f = _family(db, family_id)
    f.name = body.name.strip()
    db.commit()
    return _family_out(db, f)


@router.delete("/families/{family_id}", status_code=204)
def delete_family(family_id: int, db: Session = Depends(get_db)):
    _delete_family(db, _family(db, family_id))
    db.commit()
    return Response(status_code=204)


@router.post("/families/{family_id}/members", response_model=AdminFamilyOut)
def add_member(family_id: int, body: AdminMemberIn, db: Session = Depends(get_db)):
    f = _family(db, family_id)
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if not user:
        raise _not_found("Аккаунт с такой почтой")
    if any(m.user_id == user.id for m in f.memberships):
        raise HTTPException(status.HTTP_409_CONFLICT, "Этот человек уже в семье")
    db.add(Membership(family=f, user=user, role=body.role))
    db.commit()
    db.refresh(f)
    return _family_out(db, f)


def _member(f: Family, user_id: int) -> Membership:
    m = next((m for m in f.memberships if m.user_id == user_id), None)
    if not m:
        raise _not_found("Участник")
    return m


@router.patch("/families/{family_id}/members/{user_id}", response_model=AdminFamilyOut)
def set_role(family_id: int, user_id: int, body: RoleIn, db: Session = Depends(get_db)):
    f = _family(db, family_id)
    m = _member(f, user_id)
    if body.role == "member" and m.role == "owner" and sum(x.role == "owner" for x in f.memberships) == 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "В семье должен остаться хотя бы один владелец")
    m.role = body.role
    db.commit()
    return _family_out(db, f)


@router.delete("/families/{family_id}/members/{user_id}", status_code=204)
def remove_member(family_id: int, user_id: int, db: Session = Depends(get_db)):
    _leave(db, _member(_family(db, family_id), user_id))
    db.commit()
    return Response(status_code=204)


# --- категории (общие для всех семей) ---
def _category(db: Session, cid: int) -> Category:
    c = db.get(Category, cid)
    if not c:
        raise HTTPException(404, "Категория не найдена")
    return c


def _check_name(db: Session, name: str, exclude: int | None = None) -> str:
    name = " ".join(name.split())
    for cid, other in db.execute(select(Category.id, Category.name)):
        if cid != exclude and other.casefold() == name.casefold():
            raise HTTPException(status.HTTP_409_CONFLICT, "Такая категория уже есть")
    return name


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db)):
    counts = dict(db.execute(
        select(MedicineCategory.category_id, func.count()).group_by(MedicineCategory.category_id)
    ).all())
    cats = db.scalars(select(Category).order_by(Category.sort, Category.name))
    return [CategoryOut.model_validate(c).model_copy(update={"medicine_count": counts.get(c.id, 0)}) for c in cats]


@router.post("/categories", response_model=CategoryOut, status_code=201)
def create_category(body: CategoryIn, db: Session = Depends(get_db)):
    sort = (db.scalar(select(func.max(Category.sort))) or 0) + 1
    c = Category(sort=sort, **(body.model_dump() | {"name": _check_name(db, body.name)}))
    db.add(c)
    db.commit()
    return c


@router.put("/categories/order", response_model=list[CategoryOut])
def reorder_categories(body: CategoryOrderIn, db: Session = Depends(get_db)):
    pos = {cid: i for i, cid in enumerate(body.ids)}
    cats = list(db.scalars(select(Category)))
    for c in cats:
        c.sort = pos.get(c.id, len(pos) + c.sort)
    db.commit()
    return list_categories(db)


@router.put("/categories/{category_id}", response_model=CategoryOut)
def update_category(category_id: int, body: CategoryIn, db: Session = Depends(get_db)):
    c = _category(db, category_id)
    for k, v in (body.model_dump() | {"name": _check_name(db, body.name, exclude=c.id)}).items():
        setattr(c, k, v)
    db.commit()
    return c


@router.delete("/categories/{category_id}", status_code=204)
def delete_category(category_id: int, db: Session = Depends(get_db)):
    db.delete(_category(db, category_id))  # у лекарств всех семей эта категория просто исчезнет
    db.commit()
    return Response(status_code=204)


# --- подсказки «От чего помогает» ---
@router.get("/indication-hints", response_model=list[str])
def get_hints(db: Session = Depends(get_db)):
    return indication_hints(db)


@router.put("/indication-hints", response_model=list[str])
def put_hints(body: IndicationHintsIn, db: Session = Depends(get_db)):
    return set_indication_hints(db, body.hints)


# --- закрытый режим ---
@router.get("/access", response_model=AccessSettings)
def get_access(db: Session = Depends(get_db)):
    return access_settings(db)


@router.put("/access", response_model=AccessSettings)
def put_access(body: AccessSettings, db: Session = Depends(get_db)):
    known = set(db.scalars(select(User.id).where(User.id.in_(body.user_ids))))
    return set_access_settings(db, body.closed, [i for i in body.user_ids if i in known])


# --- режим отладки ---
@router.get("/debug", response_model=DebugSettings)
def get_debug(db: Session = Depends(get_db)):
    return DebugSettings(enabled=debug_enabled(db))


@router.get("/telegram", response_model=TelegramSettings)
def get_telegram(db: Session = Depends(get_db)):
    return TelegramSettings(enabled=telegram_switch_on(db), configured=get_settings().telegram_enabled)


@router.put("/telegram", response_model=TelegramSettings)
def put_telegram(body: TelegramSettings, db: Session = Depends(get_db)):
    """Показать или спрятать всё про Telegram. Привязанные чаты не трогаем: при включении всё вернётся."""
    return TelegramSettings(enabled=set_telegram_switch(db, body.enabled), configured=get_settings().telegram_enabled)


@router.put("/debug", response_model=DebugSettings)
def put_debug(body: DebugSettings, db: Session = Depends(get_db)):
    return DebugSettings(enabled=set_debug_enabled(db, body.enabled))


# --- платная версия ---
@router.get("/billing", response_model=BillingSettings)
def get_billing(db: Session = Depends(get_db)):
    return billing_settings(db)


@router.put("/billing", response_model=BillingSettings)
def put_billing(body: BillingSettings, db: Session = Depends(get_db)):
    return set_billing_settings(db, body)


# --- оплаты и чеки самозанятого ---
PERIOD_NAME = {"month": "1 месяц", "year": "1 год"}


def _payment_out(db: Session, p: Payment) -> AdminPaymentOut:
    user = db.get(User, p.user_id) if p.user_id else None
    out = AdminPaymentOut.model_validate(p, from_attributes=True)
    out.user_name = user.name if user else None
    return out


@router.get("/payments", response_model=list[AdminPaymentOut])
def list_payments(db: Session = Depends(get_db)):
    """Все оплаты, новые сверху. Успешные без отправленного чека — те, по которым нужно оформить чек."""
    return [_payment_out(db, p) for p in db.scalars(select(Payment).order_by(Payment.id.desc()).limit(500))]


def _payment(db: Session, pid: int) -> Payment:
    p = db.get(Payment, pid)
    if not p:
        raise _not_found("Оплата")
    return p


@router.put("/payments/{payment_id}/receipt", response_model=AdminPaymentOut)
def set_receipt(payment_id: int, body: ReceiptIn, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Сохраняет ссылку на чек из «Мой налог» и отправляет её покупателю на почту."""
    p = _payment(db, payment_id)
    if p.status not in ("succeeded", "refunded"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Чек оформляют только по оплаченным платежам")
    p.receipt_url = body.url
    if body.send_email:
        p.receipt_sent_at = datetime.now(timezone.utc)
        paid = (p.paid_at or p.created_at).strftime("%d.%m.%Y")
        tasks.add_task(
            send_mail, p.email, "Капсулка: чек по вашей оплате",
            f"Здравствуйте!\n\nЧек по оплате от {paid} ({p.amount} ₽, подписка Капсулка Плюс на {PERIOD_NAME[p.period]}):\n"
            f"{body.url}\n\nЧек оформлен самозанятым в приложении «Мой налог». Если у вас вопросы, ответьте на это письмо.\n\nКапсулка",
        )
    db.commit()
    return _payment_out(db, p)


@router.delete("/payments/{payment_id}/receipt", response_model=AdminPaymentOut)
def clear_receipt(payment_id: int, db: Session = Depends(get_db)):
    """Сбрасывает ссылку и отметку об отправке (например, чек аннулирован и оформлен заново)."""
    p = _payment(db, payment_id)
    p.receipt_url = None
    p.receipt_sent_at = None
    db.commit()
    return _payment_out(db, p)

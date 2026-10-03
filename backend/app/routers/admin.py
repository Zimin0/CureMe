"""Панель администратора: все аккаунты, все семьи и общий список категорий."""
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .. import household_check, households
from ..config import get_settings
from ..db import get_db
from ..deps import admin_user
from ..mailer import send_mail
from ..models import Category, Family, HouseholdEvent, Medicine, MedicineCategory, Membership, Payment, User
from ..schemas import (
    AccessSettings, AdminPaymentOut, AdminPlanIn, ReceiptIn, BillingSettings, DebugSettings, TelegramSettings,
    AdminFamilyOut, AdminMemberIn, AdminStats, AdminUserOut, AdminUserUpdate, CategoryIn, CategoryOrderIn,
    CategoryOut, FamilyBrief, FamilyIn, HouseholdEventOut, IndicationHintsIn, MemberOut, RoleIn,
)
from ..email_verification import mark_verified
from ..plans import PLUS, billing_settings, plus_active, set_billing_settings
from ..security import hash_password
from ..services import access_settings, debug_enabled, indication_hints, set_access_settings, set_debug_enabled, set_indication_hints, set_telegram_switch, telegram_switch_on

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
    house = u.household
    return AdminUserOut(
        id=u.id, email=u.email, name=u.name, is_admin=u.is_admin, email_verified=u.email_verified_at is not None,
        created_at=u.created_at,
        families=[FamilyBrief(id=m.family_id, name=m.family.name, role=m.role) for m in fams],
        plan=house.plan if house else "free", plus_until=house.plus_until if house else None,
        plus_active=plus_active(house), auto_renew=u.auto_renew,
        household_id=u.household_id, is_owner=u.household_role == "owner",
    )


def _family_out(db: Session, f: Family) -> AdminFamilyOut:
    count = db.scalar(select(func.count()).select_from(Medicine).where(Medicine.family_id == f.id)) or 0
    house = f.household
    owner = households.owner_of(house)
    members = households.people(house) if house else []
    return AdminFamilyOut(
        id=f.id, name=f.name, created_at=f.created_at, medicine_count=count,
        members=[
            MemberOut(user_id=u.id, name=u.name, email=u.email, role=u.household_role,
                      is_owner=u.household_role == "owner", joined_at=u.household_joined_at)
            for u in members
        ],
        plan=house.plan if house else "free", plus_until=house.plus_until if house else None,
        plus_active=plus_active(house), owner_id=owner.id if owner else None, owner_name=owner.name if owner else None,
        household_id=house.id if house else None, household_people=len(members),
        household_cabinets=len(house.cabinets) if house else 0,
    )


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
def set_user_plan(user_id: int, body: AdminPlanIn, me: User = Depends(admin_user), db: Session = Depends(get_db)):
    """Ручное включение Плюса семье человека (R16). Плюс действует на всех людей семьи и все её аптечки; выдача пишется
    в журнал семьи. Бесплатный тариф сбрасывает срок и автопродление: сохранённый способ оплаты забываем, иначе
    у семьи осталось бы включённое автопродление и кнопка «Отключить» у тарифа, которого уже нет."""
    u = _get_user(db, user_id)
    house = u.household
    if house is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "У человека нет семьи: тариф выдавать некому")
    house.plan = body.plan
    house.plus_until = body.plus_until if body.plan == PLUS else None
    house.plus_is_trial = False
    if body.plan != PLUS:
        # Карта привязана к человеку, но платит он за семью: сбрасываем у всех её людей, а не только у выбранного.
        for member in house.members:
            households.stop_autorenew(member)
    until = f" до {body.plus_until:%Y-%m-%d}" if body.plan == PLUS and body.plus_until else ""
    households.record(db, house, "plan", user=u, actor=me, detail=body.plan + until)
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
    households.delete_account(db, u, admin=True)  # владельцу при других людях владение передаётся самому давнему участнику
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
def delete_family(family_id: int, me: User = Depends(admin_user), db: Session = Depends(get_db)):
    """Администратор может удалить и последнюю аптечку семьи: человек потом создаст новую (в отличие от R24 для людей)."""
    households.delete_cabinet(db, _family(db, family_id), actor=me, force=True)
    db.commit()
    return Response(status_code=204)


@router.post("/families/{family_id}/members", response_model=AdminFamilyOut)
def add_member(family_id: int, body: AdminMemberIn, me: User = Depends(admin_user), db: Session = Depends(get_db)):
    """Вносит человека в семью этой аптечки по тем же правилам, что и приглашение (R08, лимиты R02, R03)."""
    f = _family(db, family_id)
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if not user:
        raise _not_found("Аккаунт с такой почтой")
    if user.household_id is not None and user.household_id == f.household_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Этот человек уже в семье")
    if f.household is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "У аптечки нет семьи")
    households.join(db, user, f.household, actor=me, force=True)
    if body.role == "owner":
        households.make_owner(db, f.household, user, actor=me)
    db.commit()
    db.refresh(f)
    return _family_out(db, f)


def _member(f: Family, user_id: int) -> User:
    u = next((u for u in f.household.members if u.id == user_id), None) if f.household else None
    if not u:
        raise _not_found("Участник")
    return u


@router.patch("/families/{family_id}/members/{user_id}", response_model=AdminFamilyOut)
def set_role(family_id: int, user_id: int, body: RoleIn, me: User = Depends(admin_user), db: Session = Depends(get_db)):
    """Передача владения без согласия: инструмент поддержки. Владелец один, поэтому «участник» самому владельцу не ставится."""
    f = _family(db, family_id)
    u = _member(f, user_id)
    if body.role == "member" and u.household_role == "owner":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "В семье должен быть владелец: назначьте владельцем другого человека")
    if body.role == "owner":
        households.make_owner(db, f.household, u, actor=me)
    db.commit()
    return _family_out(db, f)


@router.delete("/families/{family_id}/members/{user_id}", status_code=204)
def remove_member(family_id: int, user_id: int, me: User = Depends(admin_user), db: Session = Depends(get_db)):
    """Администратор убирает человека из семьи: тот же выход, что и у человека (R09). Владельца сначала меняют."""
    households.leave(db, _member(_family(db, family_id), user_id), actor=me, kicked=True)
    db.commit()
    return Response(status_code=204)


@router.get("/households/{household_id}/events", response_model=list[HouseholdEventOut])
def household_events(household_id: int, db: Session = Depends(get_db)):
    """Журнал семьи: вступления, выходы, передача владения, выдача Плюса (R16)."""
    rows = db.scalars(select(HouseholdEvent).where(HouseholdEvent.household_id == household_id)
                      .order_by(HouseholdEvent.id.desc()).limit(200))
    return [HouseholdEventOut.model_validate(r, from_attributes=True) for r in rows]


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

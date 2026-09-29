"""Панель администратора: все аккаунты, все семьи и общий список категорий."""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..deps import admin_user
from ..models import Category, Family, Medicine, MedicineCategory, Membership, User
from ..schemas import (
    AccessSettings, AdminPlanIn, BillingSettings,
    AdminFamilyOut, AdminMemberIn, AdminStats, AdminUserOut, AdminUserUpdate, CategoryIn, CategoryOrderIn,
    CategoryOut, FamilyBrief, FamilyIn, IndicationHintsIn, MemberOut, RoleIn,
)
from ..email_verification import mark_verified
from ..plans import billing_settings, plus_active, set_billing_settings
from ..security import hash_password
from ..services import access_settings, indication_hints, set_access_settings, set_indication_hints
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
    )


def _family_out(db: Session, f: Family) -> AdminFamilyOut:
    count = db.scalar(select(func.count()).select_from(Medicine).where(Medicine.family_id == f.id)) or 0
    members = sorted(f.memberships, key=lambda m: (m.role != "owner", m.joined_at))
    return AdminFamilyOut(
        id=f.id, name=f.name, invite_code=f.invite_code, created_at=f.created_at, medicine_count=count,
        members=[
            MemberOut(user_id=m.user_id, name=m.user.name, email=m.user.email, role=m.role, joined_at=m.joined_at)
            for m in members
        ],
        plan=f.plan, plus_until=f.plus_until, plus_active=plus_active(f),
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
@router.get("/users", response_model=list[AdminUserOut])
def list_users(db: Session = Depends(get_db)):
    users = db.scalars(
        select(User).options(selectinload(User.memberships).selectinload(Membership.family)).order_by(User.created_at)
    )
    return [_user_out(u) for u in users]


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


@router.put("/families/{family_id}/plan", response_model=AdminFamilyOut)
def set_plan(family_id: int, body: AdminPlanIn, db: Session = Depends(get_db)):
    """Ручное включение Плюса (оплаты пока нет). Бесплатный тариф сбрасывает и срок."""
    f = _family(db, family_id)
    f.plan = body.plan
    f.plus_until = body.plus_until if body.plan == "plus" else None
    db.commit()
    return _family_out(db, f)


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


# --- платная версия ---
@router.get("/billing", response_model=BillingSettings)
def get_billing(db: Session = Depends(get_db)):
    return billing_settings(db)


@router.put("/billing", response_model=BillingSettings)
def put_billing(body: BillingSettings, db: Session = Depends(get_db)):
    return set_billing_settings(db, body)

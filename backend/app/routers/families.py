from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user, family_membership, family_owner
from ..limits import ensure_can_add_member, members_full
from ..models import Family, Membership, Schedule, User
from ..plans import LIMIT_FEATURE, own_families_left, plan_out, plus_required
from ..ratelimit import client_ip, limiter
from ..schemas import AddMemberIn, FamilyIn, FamilyOut, InviteInfo, JoinIn, MemberOut, PlanOut, RoleIn
from ..security import new_invite_code
from .auth import create_family

router = APIRouter(prefix="/api", tags=["families"])


def family_out(fam: Family, role: str) -> FamilyOut:
    members = sorted(fam.memberships, key=lambda m: (m.role != "owner", m.joined_at))
    return FamilyOut(
        id=fam.id, name=fam.name, invite_code=fam.invite_code, role=role,
        members=[
            MemberOut(user_id=m.user_id, name=m.user.name, email=m.user.email, role=m.role, joined_at=m.joined_at)
            for m in members
        ],
    )


@router.post("/families", response_model=FamilyOut, status_code=201)
def new_family(body: FamilyIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    # Бесплатно — одна своя аптечка. Вступать в чужие по приглашению можно всегда,
    # а уже созданные сверх лимита аптечки не трогаем.
    if own_families_left(db, user.id) == 0:
        raise plus_required(
            LIMIT_FEATURE["own_families"],
            "В бесплатной версии можно завести одну свою аптечку. В Капсулке Плюс — сколько угодно: дача, машина, бабушка.",
        )
    fam = create_family(db, body.name.strip(), user)
    db.commit()
    return family_out(fam, "owner")


@router.get("/families/{family_id}", response_model=FamilyOut)
def get_family(m: Membership = Depends(family_membership)):
    return family_out(m.family, m.role)


@router.get("/families/{family_id}/plan", response_model=PlanOut)
def get_plan(m: Membership = Depends(family_membership), db: Session = Depends(get_db)):
    """Тариф семьи, её лимиты, что уже набрано и какие функции Плюса доступны."""
    return plan_out(db, m.family)


@router.patch("/families/{family_id}", response_model=FamilyOut)
def rename_family(body: FamilyIn, m: Membership = Depends(family_owner), db: Session = Depends(get_db)):
    m.family.name = body.name.strip()
    db.commit()
    return family_out(m.family, m.role)


@router.post("/families/{family_id}/invite", response_model=FamilyOut)
def regenerate_invite(m: Membership = Depends(family_owner), db: Session = Depends(get_db)):
    m.family.invite_code = new_invite_code()
    db.commit()
    return family_out(m.family, m.role)


@router.post("/families/{family_id}/members", response_model=FamilyOut)
def add_member(body: AddMemberIn, m: Membership = Depends(family_owner), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if not user:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Такого аккаунта пока нет. Отправьте человеку ссылку-приглашение, и он зарегистрируется по ней.",
        )
    if any(x.user_id == user.id for x in m.family.memberships):
        raise HTTPException(status.HTTP_409_CONFLICT, "Этот человек уже в семье")
    ensure_can_add_member(db, m.family)
    db.add(Membership(family=m.family, user=user, role="member"))
    db.commit()
    db.refresh(m.family)
    return family_out(m.family, m.role)


@router.patch("/families/{family_id}/members/{user_id}", response_model=FamilyOut)
def set_role(user_id: int, body: RoleIn, m: Membership = Depends(family_owner), db: Session = Depends(get_db)):
    target = next((x for x in m.family.memberships if x.user_id == user_id), None)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Участник не найден")
    owners = [x for x in m.family.memberships if x.role == "owner"]
    if body.role == "member" and target.role == "owner" and len(owners) == 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "В семье должен остаться хотя бы один владелец")
    target.role = body.role
    db.commit()
    return family_out(m.family, m.role)


@router.delete("/families/{family_id}/members/{user_id}", status_code=204)
def remove_member(user_id: int, m: Membership = Depends(family_membership), db: Session = Depends(get_db)):
    """Владелец может убрать любого; участник — только себя (выйти из семьи)."""
    if user_id != m.user_id and m.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Это может сделать только владелец семьи")
    target = next((x for x in m.family.memberships if x.user_id == user_id), None)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Участник не найден")
    others = [x for x in m.family.memberships if x.user_id != user_id]
    if target.role == "owner" and others and not any(x.role == "owner" for x in others):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Сначала назначьте другого владельца")
    family = m.family
    # Личное расписание приёма не остаётся у того, кто ушёл из аптечки (лекарства там ему больше недоступны).
    db.execute(delete(Schedule).where(Schedule.family_id == family.id, Schedule.user_id == user_id))
    db.delete(target)
    if not others:
        db.delete(family)  # последний участник ушёл — аптечка никому не нужна
    db.commit()
    return Response(status_code=204)


@router.get("/invites/{code}", response_model=InviteInfo)
def invite_info(code: str, request: Request, db: Session = Depends(get_db)):
    # Код из 8 символов не подобрать, пока попыток мало.
    limiter.hit(f"invite:{client_ip(request)}", limit=30, window=600)
    fam = db.scalar(select(Family).where(Family.invite_code == code.strip().upper()))
    if not fam:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Приглашение не найдено или устарело")
    return InviteInfo(family_name=fam.name, members=len(fam.memberships), full=members_full(db, fam))


@router.post("/families/join", response_model=FamilyOut)
def join(body: JoinIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    limiter.hit(f"invite:{client_ip(request)}", limit=30, window=600)
    fam = db.scalar(select(Family).where(Family.invite_code == body.code.strip().upper()))
    if not fam:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Приглашение не найдено или устарело")
    existing = next((x for x in fam.memberships if x.user_id == user.id), None)
    if not existing:
        ensure_can_add_member(db, fam, joining=True)
        db.add(Membership(family=fam, user=user, role="member"))
        db.commit()
        db.refresh(fam)
    return family_out(fam, existing.role if existing else "member")

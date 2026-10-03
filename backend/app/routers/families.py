from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import households
from ..db import get_db
from ..deps import current_user, family_membership, family_owner
from ..models import Family, Membership, User
from ..plans import plan_out
from ..ratelimit import client_ip, limiter
from ..schemas import FamilyIn, FamilyOut, InviteInfo, JoinIn, MemberOut, PlanOut, RoleIn
from ..security import new_invite_code

router = APIRouter(prefix="/api", tags=["families"])


def family_out(fam: Family, role: str) -> FamilyOut:
    house = fam.household
    members = households.people(house) if house else []
    return FamilyOut(
        id=fam.id, name=fam.name, invite_code=fam.invite_code, role=role,
        members=[
            MemberOut(user_id=u.id, name=u.name, email=u.email, role=u.household_role,
                      is_owner=u.household_role == "owner", joined_at=u.household_joined_at)
            for u in members
        ],
    )


@router.post("/families", response_model=FamilyOut, status_code=201)
def new_family(body: FamilyIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Новая аптечка семьи (R03): создать может любой человек семьи, пока есть место."""
    fam = households.create_cabinet(db, user, body.name.strip())
    db.commit()
    return family_out(fam, user.household_role)


@router.get("/families/{family_id}", response_model=FamilyOut)
def get_family(m: Membership = Depends(family_membership)):
    return family_out(m.family, m.role)


@router.delete("/families/{family_id}", status_code=204)
def delete_family(m: Membership = Depends(family_membership), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Удаление аптечки (R24): её создатель или владелец семьи. Последнюю аптечку семьи удалить нельзя."""
    fam = m.family
    if m.role != "owner" and fam.created_by_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Удалить аптечку может её создатель или владелец семьи")
    households.delete_cabinet(db, fam, actor=user)
    db.commit()
    return Response(status_code=204)


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


@router.patch("/families/{family_id}/members/{user_id}", response_model=FamilyOut)
def set_role(user_id: int, body: RoleIn, m: Membership = Depends(family_owner), user: User = Depends(current_user),
             db: Session = Depends(get_db)):
    """Передача владения (R02: владелец один). Прежний владелец становится участником."""
    house = m.family.household
    target = next((u for u in house.members if u.id == user_id), None)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Участник не найден")
    if body.role == "member":
        if target.household_role == "owner":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "В семье должен быть владелец: назначьте владельцем другого человека")
        return family_out(m.family, m.role)
    households.make_owner(db, house, target, actor=user)
    db.commit()
    db.refresh(m)
    return family_out(m.family, m.role)


@router.delete("/families/{family_id}/members/{user_id}", status_code=204)
def remove_member(user_id: int, m: Membership = Depends(family_membership), user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    """Владелец исключает любого участника; участник уходит сам (R09, R10). Уходящий получает личную семью и одну свою аптечку."""
    if user_id != m.user_id and m.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Это может сделать только владелец семьи")
    target = next((u for u in m.family.household.members if u.id == user_id), None)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Участник не найден")
    households.leave(db, target, actor=user, kicked=user_id != m.user_id)
    db.commit()
    return Response(status_code=204)


@router.get("/invites/{code}", response_model=InviteInfo)
def invite_info(code: str, request: Request, db: Session = Depends(get_db)):
    # Код из 8 символов не подобрать, пока попыток мало.
    limiter.hit(f"invite:{client_ip(request)}", limit=30, window=600)
    fam = db.scalar(select(Family).where(Family.invite_code == code.strip().upper()))
    if not fam or not fam.household:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Приглашение не найдено или устарело")
    house = fam.household
    return InviteInfo(family_name=fam.name, members=len(house.members), full=households.members_full(db, house))


@router.post("/families/join", response_model=FamilyOut)
def join(body: JoinIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    limiter.hit(f"invite:{client_ip(request)}", limit=30, window=600)
    fam = db.scalar(select(Family).where(Family.invite_code == body.code.strip().upper()))
    if not fam or not fam.household:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Приглашение не найдено или устарело")
    households.join(db, user, fam.household, actor=user)
    db.commit()
    db.refresh(fam)
    return family_out(fam, user.household_role)

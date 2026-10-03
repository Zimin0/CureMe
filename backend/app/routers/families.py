from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from .. import households
from ..db import get_db
from ..deps import current_user, family_membership, family_owner
from ..models import Family, Membership, User
from ..plans import plan_out
from ..ratelimit import client_ip, limiter
from ..schemas import FamilyIn, FamilyOut, InviteInfo, JoinIn, MemberOut, PlanOut, RoleIn

router = APIRouter(prefix="/api", tags=["families"])


def family_out(fam: Family, role: str, db: Session, ensure_invite: bool = False) -> FamilyOut:
    """Семья для экрана. Приглашение видит только владелец (R04): ensure_invite выпускает его, если действующего нет."""
    house = fam.household
    members = households.people(house) if house else []
    invite = None
    if role == "owner" and house:
        invite = households.ensure_invite(db, house, households.owner_of(house)) if ensure_invite else households.active_invite(db, house)
    return FamilyOut(
        id=fam.id, name=fam.name, role=role,
        invite_code=invite.code if invite else None, invite_expires_at=invite.expires_at if invite else None,
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
    return family_out(fam, user.household_role, db)


@router.get("/families/{family_id}", response_model=FamilyOut)
def get_family(m: Membership = Depends(family_membership), db: Session = Depends(get_db)):
    out = family_out(m.family, m.role, db, ensure_invite=True)
    db.commit()  # владельцу могла выпуститься новая ссылка
    return out


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
    return family_out(m.family, m.role, db)


@router.post("/families/{family_id}/invite", response_model=FamilyOut)
def regenerate_invite(m: Membership = Depends(family_owner), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Новое приглашение (R04): прежнее перестаёт работать. Только владелец семьи."""
    households.issue_invite(db, m.family.household, user)
    db.commit()
    return family_out(m.family, m.role, db)


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
        return family_out(m.family, m.role, db)
    households.make_owner(db, house, target, actor=user)
    db.commit()
    db.refresh(m)
    return family_out(m.family, m.role, db)


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
    """Что видит тот, кому дали ссылку (R04): название аптечки, кто приглашает и есть ли место. Больше ничего."""
    # Код из 8 символов не подобрать, пока попыток мало.
    limiter.hit(f"invite:{client_ip(request)}", limit=30, window=600)
    inv = households.find_invite(db, code)
    if inv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Приглашение не найдено или устарело")
    house = inv.household
    owner = households.owner_of(house)
    cabinets = households.cabinets_of(house)
    return InviteInfo(family_name=cabinets[0].name if cabinets else "семью", owner_name=owner.name if owner else "",
                      full=households.members_full(db, house))


@router.post("/families/join", response_model=FamilyOut)
def join(body: JoinIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    limiter.hit(f"invite:{client_ip(request)}", limit=30, window=600)
    inv = households.claim_invite(db, body.code, user)
    if inv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Приглашение не найдено или устарело")
    house = inv.household
    if user.household is house:  # свой код владельца или повторный переход: ничего не сгорает
        return family_out(households.cabinets_of(house)[0], user.household_role, db)
    households.join(db, user, house, actor=user)  # отказ (нет места, чужая семья) откатывает всё: код не сгорает (R04-T5)
    households.use_invite(inv, user)
    db.commit()
    fam = households.cabinets_of(user.household)[0]
    return family_out(fam, user.household_role, db)

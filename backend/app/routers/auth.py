from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..legal import CONSENT_VERSION
from ..models import Family, Membership, User, utcnow
from ..schemas import ConsentIn, DeleteAccountIn, FamilyBrief, LoginIn, MeOut, RegisterIn, TokenOut, UserUpdate
from ..security import create_token, hash_password, new_invite_code, verify_password
from ..seed import ensure_default_categories
from .admin import _leave

router = APIRouter(prefix="/api/auth", tags=["auth"])


def create_family(db: Session, name: str, owner: User) -> Family:
    fam = Family(name=name, invite_code=new_invite_code())
    fam.memberships.append(Membership(user=owner, role="owner"))
    db.add(fam)
    ensure_default_categories(db)
    return fam


def me_out(user: User) -> MeOut:
    fams = sorted(user.memberships, key=lambda m: m.joined_at)
    return MeOut(
        id=user.id, email=user.email, name=user.name, is_admin=user.is_admin,
        consent_needed=user.consent_version != CONSENT_VERSION,
        families=[FamilyBrief(id=m.family_id, name=m.family.name, role=m.role) for m in fams],
    )


@router.post("/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    # Без согласия (152-ФЗ, ст. 9 и 10) хранить почту и сведения об аптечке нельзя.
    if not body.consent:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Нужно согласие на обработку персональных данных")
    email = body.email.lower()
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Аккаунт с такой почтой уже есть")
    family = None
    if body.invite_code:
        family = db.scalar(select(Family).where(Family.invite_code == body.invite_code.strip().upper()))
        if not family:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Код приглашения не найден")

    first = db.scalar(select(User.id).limit(1)) is None  # первый аккаунт — администратор
    user = User(email=email, name=body.name.strip(), password_hash=hash_password(body.password), is_admin=first,
                consent_at=utcnow(), consent_version=CONSENT_VERSION)
    db.add(user)
    if family:
        db.add(Membership(family=family, user=user, role="member"))
    else:
        create_family(db, f"Семья {user.name}", user)
    db.commit()
    db.refresh(user)
    return TokenOut(access_token=create_token(user.id), user=me_out(user))


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверная почта или пароль")
    return TokenOut(access_token=create_token(user.id), user=me_out(user))


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(current_user)):
    return me_out(user)


@router.patch("/me", response_model=MeOut)
def update_me(body: UserUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.name:
        user.name = body.name.strip()
    if body.password:
        user.password_hash = hash_password(body.password)
    db.commit()
    return me_out(user)


@router.post("/consent", response_model=MeOut)
def give_consent(body: ConsentIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Согласие для тех, кто зарегистрировался раньше, или после смены его текста."""
    if not body.consent:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Нужно согласие на обработку персональных данных")
    user.consent_at, user.consent_version = utcnow(), CONSENT_VERSION
    db.commit()
    return me_out(user)


@router.delete("/me", status_code=204)
def delete_me(body: DeleteAccountIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Удаление аккаунта — это и отзыв согласия (152-ФЗ, ст. 9 и 21): данные стираются сразу.

    Из каждой семьи человек выходит как при «Покинуть семью»: семья без участников удаляется
    вместе с аптечкой и фото, а общие лекарства остальных участников остаются.
    """
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Неверный пароль")
    for m in list(user.memberships):
        _leave(db, m)
    db.flush()
    db.expire(user, ["memberships"])
    db.delete(user)
    db.commit()
    return Response(status_code=204)

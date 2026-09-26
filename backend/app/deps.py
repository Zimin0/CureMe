from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Family, Membership, User
from .security import decode_token

bearer = HTTPBearer(auto_error=False)


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)
) -> User:
    user_id = decode_token(creds.credentials) if creds else None
    user = db.get(User, user_id) if user_id else None
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Нужно войти в аккаунт")
    return user


def family_membership(
    family_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> Membership:
    m = db.scalar(select(Membership).where(Membership.family_id == family_id, Membership.user_id == user.id))
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Семья не найдена")
    return m


def family_owner(m: Membership = Depends(family_membership)) -> Membership:
    if m.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Это может сделать только владелец семьи")
    return m


def get_family(m: Membership = Depends(family_membership)) -> Family:
    return m.family

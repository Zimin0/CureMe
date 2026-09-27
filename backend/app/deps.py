from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import Family, Membership, User
from .security import decode_token
from .services import has_access

bearer = HTTPBearer(auto_error=False)


def signed_in_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)
) -> User:
    """Любой вошедший, даже без доступа в закрытом режиме: ему можно посмотреть профиль,
    дать согласие и удалить аккаунт (права по 152-ФЗ не зависят от закрытого режима)."""
    user_id = decode_token(creds.credentials) if creds else None
    user = db.get(User, user_id) if user_id else None
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Нужно войти в аккаунт")
    if not user.is_admin and user.email.lower() in {e.lower() for e in get_settings().admin_emails}:
        user.is_admin = True
        db.commit()
    return user


def current_user(user: User = Depends(signed_in_user), db: Session = Depends(get_db)) -> User:
    """Вошедший, которому открыт сайт. Остальные получают 403 с кодом closed."""
    if not has_access(db, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Сайт в разработке: доступ пока только у участников теста")
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нужны права администратора")
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

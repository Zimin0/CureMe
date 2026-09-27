from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import Family, Membership, User
from ..ratelimit import client_ip, limiter
from ..schemas import FamilyBrief, LoginIn, MeOut, RegisterIn, TokenOut, UserUpdate
from ..security import burn_password_check, create_token, hash_password, new_invite_code, verify_password
from ..seed import ensure_default_categories

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
        families=[FamilyBrief(id=m.family_id, name=m.family.name, role=m.role) for m in fams],
    )


@router.post("/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    limiter.hit(f"register:{client_ip(request)}", limit=10, window=3600)
    email = body.email.lower()
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Аккаунт с такой почтой уже есть")
    family = None
    if body.invite_code:
        family = db.scalar(select(Family).where(Family.invite_code == body.invite_code.strip().upper()))
        if not family:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Код приглашения не найден")

    first = db.scalar(select(User.id).limit(1)) is None  # первый аккаунт — администратор
    user = User(email=email, name=body.name.strip(), password_hash=hash_password(body.password), is_admin=first)
    db.add(user)
    if family:
        db.add(Membership(family=family, user=user, role="member"))
    else:
        create_family(db, f"Семья {user.name}", user)
    db.commit()
    db.refresh(user)
    return TokenOut(access_token=create_token(user.id, user.token_version), user=me_out(user))


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    email = body.email.lower()
    # Перебор паролей: не больше 10 попыток в минуту с одного адреса и 20 за 15 минут на одну почту.
    limiter.hit(f"login-ip:{client_ip(request)}", limit=10, window=60)
    limiter.hit(f"login-email:{email}", limit=20, window=900)
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if not user:
        burn_password_check(body.password)
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверная почта или пароль")
    return TokenOut(access_token=create_token(user.id, user.token_version), user=me_out(user))


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(current_user)):
    return me_out(user)


@router.patch("/me", response_model=MeOut)
def update_me(body: UserUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.name:
        user.name = body.name.strip()
    token = None
    if body.password:
        if not body.current_password or not verify_password(body.current_password, user.password_hash):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Текущий пароль указан неверно")
        user.password_hash = hash_password(body.password)
        user.token_version += 1  # выходим на всех остальных устройствах
        token = create_token(user.id, user.token_version)
    db.commit()
    return me_out(user).model_copy(update={"access_token": token})

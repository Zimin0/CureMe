from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import compression, households
from ..db import get_db
from ..deps import signed_in_user
from ..email_verification import (
    clear_reset, code_matches, issue_code, issue_reset_code, mark_verified, needs_verification, reset_code_ok,
    send_password_reset, send_verification,
)
from ..legal import CONSENT_VERSION
from ..models import User, utcnow
from ..plans import billing_settings, grant_trial, own_families_left, plus_active
from ..ratelimit import client_ip, limiter
from ..schemas import (
    MIN_ADMIN_PASSWORD, AccessOut, ConsentIn, DeleteAccountIn, FamilyBrief, LoginIn, MeOut, PasswordResetConfirmIn,
    PasswordResetRequestIn, RegisterIn, TokenOut, UserUpdate, VerifyEmailIn,
)
from ..security import burn_password_check, create_token, hash_password, verify_password
from .illness import drop_user_files as drop_illness_files
from ..services import access_settings, debug_enabled, has_access, telegram_active

router = APIRouter(prefix="/api/auth", tags=["auth"])


def me_out(user: User, db: Session) -> MeOut:
    fams = sorted(user.memberships, key=lambda m: m.joined_at)
    transfer = households.pending_transfer(db, user.household)
    return MeOut(
        id=user.id, email=user.email, name=user.name, is_admin=user.is_admin,
        consent_needed=user.consent_version != CONSENT_VERSION,
        access_blocked=not has_access(db, user),
        email_verified=user.email_verified_at is not None,
        verification_needed=needs_verification(user),
        families=[FamilyBrief(id=m.family_id, name=m.family.name, role=m.role, status=m.family.status) for m in fams],
        owner_transfer_waiting=transfer is not None and transfer.to_user_id == user.id,
        own_families_left=own_families_left(db, user.id),
        next_change_at=households.next_change_at(user),
        plus_active=plus_active(user),
        plus_ending=compression.banner(db, user),
    )


@router.post("/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    # Без согласия (152-ФЗ, ст. 9 и 10) хранить почту и сведения об аптечке нельзя.
    if not body.consent:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Нужно согласие на обработку персональных данных")
    if access_settings(db)["closed"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Сайт в разработке, регистрация пока закрыта")
    limiter.hit(f"register:{client_ip(request)}", limit=10, window=3600)
    email = body.email.lower()
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Аккаунт с такой почтой уже есть")
    house = invite = None
    if body.invite_code:
        invite = households.claim_invite(db, body.invite_code)
        if invite is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Код приглашения не найден, уже использован или устарел")
        house = invite.household
        households.ensure_room_for_person(db, house, joining=True)

    first = db.scalar(select(User.id).limit(1)) is None  # первый аккаунт — администратор
    user = User(email=email, name=body.name.strip(), password_hash=hash_password(body.password), is_admin=first,
                consent_at=utcnow(), consent_version=CONSENT_VERSION)
    db.add(user)
    try:
        db.flush()
    except IntegrityError:  # два запроса с одной почтой одновременно: проверка выше обоих пропустила, базу не обманешь
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Аккаунт с такой почтой уже есть") from None
    if house:
        households.attach(db, user, house)
        households.use_invite(invite, user)  # код закреплён за этой регистрацией: второй раз не сработает (R04)
    else:
        households.create_personal(db, user)
    code = issue_code(user) if needs_verification(user) else None
    if code is None:
        grant_trial(db, user)  # почту не проверяем (нет SMTP): подарок сразу; иначе его даёт подтверждение почты
    db.commit()
    db.refresh(user)
    if code:
        # Письмо уходит уже после ответа: человек не ждёт почтовый сервер.
        background.add_task(send_verification, user.email, user.name, code)
    return TokenOut(access_token=create_token(user.id, user.token_version), user=me_out(user, db))


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
    return TokenOut(access_token=create_token(user.id, user.token_version), user=me_out(user, db))


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(signed_in_user), db: Session = Depends(get_db)):
    return me_out(user, db)


@router.patch("/me", response_model=MeOut)
def update_me(body: UserUpdate, user: User = Depends(signed_in_user), db: Session = Depends(get_db)):
    if body.name:
        user.name = body.name.strip()
    token = None
    if body.password:
        # С украденным токеном нельзя подбирать текущий пароль, чтобы сменить его и забрать аккаунт насовсем.
        limiter.hit(f"change-password:{user.id}", limit=5, window=900)
        if user.is_admin and len(body.password) < MIN_ADMIN_PASSWORD:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Администратору нужен пароль не короче {MIN_ADMIN_PASSWORD} символов")
        if not body.current_password or not verify_password(body.current_password, user.password_hash):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Текущий пароль указан неверно")
        user.password_hash = hash_password(body.password)
        user.token_version += 1  # выходим на всех остальных устройствах
        token = create_token(user.id, user.token_version)
    db.commit()
    return me_out(user, db).model_copy(update={"access_token": token})


@router.post("/consent", response_model=MeOut)
def give_consent(body: ConsentIn, user: User = Depends(signed_in_user), db: Session = Depends(get_db)):
    """Согласие для тех, кто зарегистрировался раньше, или после смены его текста."""
    if not body.consent:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Нужно согласие на обработку персональных данных")
    user.consent_at, user.consent_version = utcnow(), CONSENT_VERSION
    db.commit()
    return me_out(user, db)


@router.delete("/me", status_code=204)
def delete_me(body: DeleteAccountIn, user: User = Depends(signed_in_user), db: Session = Depends(get_db)):
    """Удаление аккаунта — это и отзыв согласия (152-ФЗ, ст. 9 и 21): данные стираются сразу.

    Аптечки, которые создал человек, остаются семье, а общие лекарства других участников остаются. Если он
    последний, семья удаляется целиком вместе с аптечками и фото. Владелец при других людях сначала передаёт владение.
    """
    # С украденным токеном нельзя подбирать пароль, чтобы стереть чужой аккаунт.
    limiter.hit(f"delete-me:{user.id}", limit=5, window=900)
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Неверный пароль")
    drop_illness_files(db, user)
    households.delete_account(db, user)
    db.delete(user)
    db.commit()
    return Response(status_code=204)


@router.post("/verify-email/resend", status_code=204)
def resend_verification(background: BackgroundTasks,
                        user: User = Depends(signed_in_user), db: Session = Depends(get_db)):
    """Отправить письмо с новым кодом. Старый код перестаёт работать."""
    if user.email_verified_at:
        raise HTTPException(status.HTTP_409_CONFLICT, "Почта уже подтверждена")
    # Чтобы через нас нельзя было засыпать чей-то ящик письмами: раз в минуту и не больше 5 в час.
    limiter.hit(f"verify-resend-min:{user.id}", limit=1, window=60)
    limiter.hit(f"verify-resend-hour:{user.id}", limit=5, window=3600)
    limiter.hit(f"verify-resend-day:{user.id}", limit=10, window=86400)
    code = issue_code(user)
    db.commit()
    background.add_task(send_verification, user.email, user.name, code)
    return Response(status_code=204)


@router.post("/verify-email", status_code=204)
def verify_email(body: VerifyEmailIn, user: User = Depends(signed_in_user), db: Session = Depends(get_db)):
    """Ввод кода из письма. Попыток мало, чтобы шестизначный код нельзя было подобрать."""
    limiter.hit(f"verify-email:{user.id}", limit=5, window=900)
    if user.email_verified_at:
        raise HTTPException(status.HTTP_409_CONFLICT, "Почта уже подтверждена")
    ok, expired = code_matches(user, body.code)
    if not ok:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Код неверный или уже использован")
    if expired:
        raise HTTPException(status.HTTP_410_GONE, "Код устарел. Отправьте письмо ещё раз")
    mark_verified(user)
    grant_trial(db, user)
    db.commit()
    return Response(status_code=204)


@router.post("/logout-all", response_model=TokenOut)
def logout_everywhere(user: User = Depends(signed_in_user), db: Session = Depends(get_db)):
    """«Выйти на всех устройствах»: все выданные раньше токены перестают действовать, этому устройству выдаём новый."""
    user.token_version += 1
    db.commit()
    return TokenOut(access_token=create_token(user.id, user.token_version), user=me_out(user, db))


@router.post("/password-reset/request", status_code=204)
def password_reset_request(
    body: PasswordResetRequestIn, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)
):
    """Отправляет на почту код для восстановления пароля. Ответ всегда один и тот же: по нему нельзя узнать,
    есть ли такая почта. Лимиты не дают засыпать письмами чужой ящик."""
    email = body.email.lower()
    limiter.hit(f"reset-ip:{client_ip(request)}", limit=10, window=3600)
    limiter.hit(f"reset-email-hour:{email}", limit=3, window=3600)
    limiter.hit(f"reset-email-day:{email}", limit=6, window=86400)
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user:
        code = issue_reset_code(user)
        db.commit()
        background.add_task(send_password_reset, user.email, user.name, code)
    return Response(status_code=204)


@router.post("/password-reset/confirm", status_code=204)
def password_reset_confirm(body: PasswordResetConfirmIn, request: Request, db: Session = Depends(get_db)):
    """Новый пароль по коду из письма. Пароль меняется, все старые входы закрываются, а почта считается подтверждённой."""
    email = body.email.lower()
    limiter.hit(f"reset-confirm-ip:{client_ip(request)}", limit=20, window=900)
    limiter.hit(f"reset-confirm-email:{email}", limit=10, window=900)
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if not user:
        burn_password_check(body.password)
    ok = user is not None and reset_code_ok(user, body.code)
    if not ok:
        if user:
            db.commit()  # неверный ввод записан в счётчик попыток
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Код неверный, устарел или уже использован. Запросите новый")
    if user.is_admin and len(body.password) < MIN_ADMIN_PASSWORD:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Администратору нужен пароль не короче {MIN_ADMIN_PASSWORD} символов")
    user.password_hash = hash_password(body.password)
    user.token_version += 1  # старые входы закрываются: пароль могли знать посторонние
    clear_reset(user)
    if user.email_verified_at is None:
        mark_verified(user)  # код пришёл на эту почту: владение доказано
        grant_trial(db, user)
    db.commit()
    return Response(status_code=204)


@router.get("/access", response_model=AccessOut)
def access(db: Session = Depends(get_db)):
    """Открыт ли сайт для всех и включён ли режим отладки. Нужен страницам входа и регистрации до того, как человек вошёл."""
    billing = billing_settings(db)
    return AccessOut(
        closed=access_settings(db)["closed"], debug=debug_enabled(db), telegram=telegram_active(db),
        trial_days=billing.trial_days,
        price_month=billing.price_month if billing.enabled else None,
        price_year=billing.price_year if billing.enabled else None,
        billing_enabled=billing.enabled, listed_price_month=billing.price_month, listed_price_year=billing.price_year,
    )

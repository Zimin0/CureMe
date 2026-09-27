import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import get_settings

ALGORITHM = "HS256"
# bcrypt учитывает только первые 72 байта пароля, а bcrypt 5 на более длинном падает.
# Кириллица занимает 2 байта на букву, поэтому это ~36 русских символов.
MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    if len(password.encode()) > MAX_PASSWORD_BYTES:
        return False
    return bcrypt.checkpw(password.encode(), hashed.encode())


# Хеш-пустышка: если почты нет, всё равно тратим время на проверку пароля,
# чтобы по скорости ответа нельзя было узнать, зарегистрирована ли почта.
_DUMMY_HASH = bcrypt.hashpw(b"dummy-password", bcrypt.gensalt()).decode()


def burn_password_check(password: str) -> None:
    verify_password(password, _DUMMY_HASH)


def create_token(user_id: int, token_version: int = 0) -> str:
    s = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(days=s.token_ttl_days)
    payload = {"sub": str(user_id), "exp": exp, "tv": token_version}
    return jwt.encode(payload, s.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> tuple[int, int] | None:
    """(id пользователя, версия токена) или None, если токен поддельный или просрочен."""
    try:
        payload = jwt.decode(
            token, get_settings().secret_key, algorithms=[ALGORITHM], options={"require": ["exp", "sub"]},
        )
        return int(payload["sub"]), int(payload.get("tv", 0))
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        return None


def new_invite_code() -> str:
    # Без похожих символов (0/O, 1/I), чтобы код было легко продиктовать.
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(8))

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CUREME_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./cureme.db"
    secret_key: str = "dev-only-secret-change-me-in-production-please"
    token_ttl_days: int = 30
    # Сколько дней до окончания срока считаем «скоро истекает».
    expiring_soon_days: int = 30
    # Внешний поиск названия по штрихкоду (Open Food Facts). Можно выключить.
    remote_lookup: bool = True
    # Каталог со сборкой фронтенда; если есть, FastAPI отдаёт его как статику.
    frontend_dist: Path = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    # Куда складывать фото лекарств (в Docker это том /data).
    media_dir: Path = Path("./media")
    max_photo_mb: int = 8
    # Почты, которые всегда получают права администратора (запасной вход, если первый аккаунт потерян).
    # Первый зарегистрированный аккаунт становится администратором и без этого.
    admin_emails: list[str] = []
    cors_origins: list[str] = ["http://localhost:5173"]
    # Ограничение частоты входа, регистрации и проверки кодов приглашений (см. ratelimit.py).
    rate_limit: bool = True
    # Интерактивная документация API (/docs, /openapi.json). На сервере выключена.
    api_docs: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()

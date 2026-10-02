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

    # Адрес сайта для ссылок в письмах, например https://kapsulka.ru. Пусто — берём из запроса.
    public_url: str = ""
    # Коды подтверждения сайта из Яндекс Вебмастера и Google Search Console (мета-тег на главной). Пусто — тега нет.
    yandex_verification: str = ""
    google_verification: str = ""
    # Почта (SMTP). Пока smtp_host пуст, письма не отправляются, а пишутся в лог приложения.
    smtp_host: str = ""
    smtp_port: int = 465
    # ssl — шифрование сразу (порт 465), starttls — после приветствия (порт 587), none — без шифрования.
    smtp_security: str = "ssl"
    smtp_user: str = ""
    smtp_password: str = ""
    # Отправитель, например noreply@kapsulka.ru. Пусто — smtp_user.
    mail_from: str = ""
    mail_from_name: str = "Капсулка"
    # Требовать подтверждения почты. Не задано — требуем, только если настроен SMTP:
    # без него письмо не дойдёт, и новые люди застряли бы на экране «Подтвердите почту».
    email_verification: bool | None = None
    # Сколько минут действует код подтверждения из письма.
    email_code_ttl_minutes: int = 30

    # Напоминания «скоро закончится» и «истекает срок» (reminders.py).
    # Фоновые задачи внутри приложения: ежедневная рассылка и приём сообщений Telegram-бота.
    background_jobs: bool = True
    # В котором часу по Москве рассылать напоминания.
    reminders_hour: int = 10
    # Telegram-бот: токен от @BotFather и имя бота без @ (для ссылки t.me/имя). Пусто — Telegram выключен.
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""
    # Сколько минут действует ссылка привязки Telegram.
    telegram_link_ttl_minutes: int = 60

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_bot_username)

    @property
    def email_verification_required(self) -> bool:
        return self.email_verification if self.email_verification is not None else bool(self.smtp_host)


@lru_cache
def get_settings() -> Settings:
    return Settings()

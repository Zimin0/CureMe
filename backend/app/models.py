from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON, BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    # Администратор управляет всеми аккаунтами, семьями и общим списком категорий.
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    # Растёт при смене пароля: все выданные раньше токены (входы на других устройствах) перестают действовать.
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Когда и какую редакцию согласия на обработку персональных данных человек принял (152-ФЗ).
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consent_version: Mapped[str | None] = mapped_column(String(20))
    # Тариф аккаунта: free | plus. Плюс действует на все аптечки, где человек главный владелец. Правила — в plans.py.
    plan: Mapped[str] = mapped_column(String(16), default="free", server_default="free")
    # До какого момента действует Плюс. Пусто при plan = plus — бессрочно.
    plus_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Когда аккаунту выдан пробный Плюс. Выдаётся один раз: повторно (в том числе после окончания) не дарим.
    trial_granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Когда человек перешёл по ссылке из письма. Пусто — почта не подтверждена.
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Хеш (SHA-256) одноразового токена из последнего письма и время отправки: сам токен в базе не храним,
    # чтобы утёкшая копия базы не давала подтверждать чужие почты.
    email_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    email_token_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Автопродление Плюса: человек сам включил галочку при оплате. Данные карты у нас не хранятся,
    # только идентификатор сохранённого способа оплаты ЮKassa (pay_method_id).
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    pay_method_id: Mapped[str | None] = mapped_column(String(100))
    renew_period: Mapped[str | None] = mapped_column(String(8))  # month | year
    # Для какого окончания Плюса (plus_until) и когда отправлено письмо «через 3 дня спишем».
    renew_notified_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    renew_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    memberships: Mapped[list["Membership"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Payment(Base):
    """Оплата Плюса через ЮKassa. Записи не удаляются вместе с аккаунтом: они нужны для чеков и учёта доходов."""

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    email: Mapped[str] = mapped_column(String(255))  # почта плательщика на момент оплаты: сюда уходит чек
    yk_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    period: Mapped[str] = mapped_column(String(8))  # month | year
    amount: Mapped[int] = mapped_column(Integer)  # рублей
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | succeeded | canceled | refunded
    recurring: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")  # автопродление
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Чек самозанятого из «Мой налог»: ссылка, которую админ вставил, и когда она ушла покупателю.
    receipt_url: Mapped[str | None] = mapped_column(String(500))
    receipt_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Family(Base):
    __tablename__ = "families"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    invite_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    memberships: Mapped[list["Membership"]] = relationship(back_populates="family", cascade="all, delete-orphan")
    medicines: Mapped[list["Medicine"]] = relationship(back_populates="family", cascade="all, delete-orphan")


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("family_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16), default="member")  # owner | member
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    family: Mapped[Family] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")


class Category(Base):
    """Категории общие для всех семей; менять их может только администратор."""

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True)
    icon: Mapped[str] = mapped_column(String(16), default="💊")
    color: Mapped[str] = mapped_column(String(16), default="#0f9d8a")
    sort: Mapped[int] = mapped_column(Integer, default=0)


class AppSetting(Base):
    """Настройки приложения, которые меняет администратор: ключ → значение в JSON.

    Строки нет — действует значение по умолчанию из seed.py.
    """

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)


class Medicine(Base):
    __tablename__ = "medicines"

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    form: Mapped[str | None] = mapped_column(String(60))           # таблетки, сироп, мазь…
    dosage: Mapped[str | None] = mapped_column(String(60))         # 500 мг
    active_ingredient: Mapped[str | None] = mapped_column(String(200))
    manufacturer: Mapped[str | None] = mapped_column(String(200))
    indications: Mapped[str] = mapped_column(Text, default="")     # «от чего помогает»
    contraindications: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    unit: Mapped[str] = mapped_column(String(20), default="шт")
    min_quantity: Mapped[float | None] = mapped_column(Float)      # порог «заканчивается»
    blister_size: Mapped[int | None] = mapped_column(Integer)      # таблеток в одном блистере
    gtin: Mapped[str | None] = mapped_column(String(14), index=True)
    photo: Mapped[str | None] = mapped_column(String(64))           # имя файла в media_dir
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    family: Mapped[Family] = relationship(back_populates="medicines")
    # До трёх категорий; первая (position = 0) — основная, её значок и цвет показываются в списках.
    category_links: Mapped[list["MedicineCategory"]] = relationship(
        cascade="all, delete-orphan", order_by="MedicineCategory.position"
    )
    packages: Mapped[list["Package"]] = relationship(
        back_populates="medicine", cascade="all, delete-orphan", order_by="Package.expiry_date"
    )
    marks: Mapped[list["UserMark"]] = relationship(cascade="all, delete-orphan")

    @property
    def categories(self) -> list[Category]:
        return [link.category for link in self.category_links]

    @property
    def category(self) -> Category | None:
        return self.category_links[0].category if self.category_links else None


class MedicineCategory(Base):
    """Связь «лекарство — категория» (многие ко многим) с порядком: первая категория основная."""

    __tablename__ = "medicine_categories"

    medicine_id: Mapped[int] = mapped_column(ForeignKey("medicines.id", ondelete="CASCADE"), primary_key=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)

    category: Mapped[Category] = relationship(lazy="joined")


class Package(Base):
    """Конкретная упаковка: у каждой свой срок годности и остаток."""

    __tablename__ = "packages"

    id: Mapped[int] = mapped_column(primary_key=True)
    medicine_id: Mapped[int] = mapped_column(ForeignKey("medicines.id", ondelete="CASCADE"), index=True)
    quantity: Mapped[float] = mapped_column(Float, default=1)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    opened_at: Mapped[date | None] = mapped_column(Date)
    serial: Mapped[str | None] = mapped_column(String(64), index=True)   # из DataMatrix
    batch: Mapped[str | None] = mapped_column(String(64))
    location: Mapped[str | None] = mapped_column(String(100))
    added_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    medicine: Mapped[Medicine] = relationship(back_populates="packages")


class UserMark(Base):
    """Личные отметки участника: «избранное» и «помогает мне»."""

    __tablename__ = "user_marks"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    medicine_id: Mapped[int] = mapped_column(ForeignKey("medicines.id", ondelete="CASCADE"), primary_key=True)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    helps_me: Mapped[bool] = mapped_column(Boolean, default=False)
    personal_note: Mapped[str] = mapped_column(Text, default="")


class Intake(Base):
    """Запись в истории приёма: кто, когда и сколько принял.

    Повторные нажатия «Принял» одного лекарства одним человеком в течение минуты
    складываются в одну запись (amount растёт, last_at сдвигается).
    Название лекарства копируется, чтобы история не пропала, если лекарство удалят.
    """

    __tablename__ = "intakes"

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"), index=True)
    medicine_id: Mapped[int | None] = mapped_column(ForeignKey("medicines.id", ondelete="SET NULL"), index=True)
    medicine_name: Mapped[str] = mapped_column(String(200))
    unit: Mapped[str] = mapped_column(String(20), default="шт")
    # Удалил аккаунт — удаляется и его история приёма (это его личные данные).
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    amount: Mapped[float] = mapped_column(Float)
    # Комментарий видит только тот, кто его написал: как личная заметка в UserMark.
    comment: Mapped[str] = mapped_column(Text, default="", server_default="")
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    last_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)  # последнее нажатие

    user: Mapped[User] = relationship()


class Schedule(Base):
    """Назначенный приём: лекарство, доза и повторение. Личное расписание человека, другие его не видят.

    В какие дни и часы пить — в slots (одна строка на «день недели + время»). Так можно убрать
    «каждый вторник в 16:00», не трогая остальные приёмы этого лекарства.
    Название лекарства копируется, чтобы расписание не потеряло подпись, если лекарство удалят.
    """

    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    medicine_id: Mapped[int | None] = mapped_column(ForeignKey("medicines.id", ondelete="SET NULL"), index=True)
    medicine_name: Mapped[str] = mapped_column(String(200))
    unit: Mapped[str] = mapped_column(String(20), default="шт")
    amount: Mapped[float] = mapped_column(Float, default=1)              # сколько принимать за раз
    start_date: Mapped[date] = mapped_column(Date)                        # с какого дня (по Москве)
    end_date: Mapped[date | None] = mapped_column(Date)                   # по какой день включительно; None — бессрочно
    every_weeks: Mapped[int] = mapped_column(Integer, default=1)          # 1 — каждую неделю, 2 — через неделю…
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    slots: Mapped[list["ScheduleSlot"]] = relationship(
        back_populates="schedule", cascade="all, delete-orphan", order_by="ScheduleSlot.weekday, ScheduleSlot.minute")


class ScheduleSlot(Base):
    """Один повторяющийся приём: день недели (0 — понедельник) и время в минутах от полуночи по Москве."""

    __tablename__ = "schedule_slots"
    __table_args__ = (UniqueConstraint("schedule_id", "weekday", "minute"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("schedules.id", ondelete="CASCADE"), index=True)
    weekday: Mapped[int] = mapped_column(Integer)
    minute: Mapped[int] = mapped_column(Integer)

    schedule: Mapped[Schedule] = relationship(back_populates="slots")


class SchedulePrefs(Base):
    """Уведомления о приёме по расписанию: себе на почту и доверенному человеку. Строки нет — выключено."""

    __tablename__ = "schedule_prefs"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)              # письма себе
    lead_minutes: Mapped[int] = mapped_column(Integer, default=10)             # напомнить за сколько минут до приёма
    repeat_minutes: Mapped[int] = mapped_column(Integer, default=10)           # напомнить снова через сколько минут, если приём не отмечен
    escalate_enabled: Mapped[bool] = mapped_column(Boolean, default=False)     # сообщать доверенному человеку
    escalate_minutes: Mapped[int] = mapped_column(Integer, default=10)         # через сколько минут после повторного напоминания
    share_medicine_name: Mapped[bool] = mapped_column(Boolean, default=False)  # называть лекарство в письме доверенному
    # Когда пользователь отдельно разрешил сообщать доверенному, что приём не отмечен (Согласие, п. 4.1):
    # письмо доверенному раскрывает сведения о здоровье. Без этой даты такие письма не уходят.
    escalate_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalate_consent_version: Mapped[str | None] = mapped_column(String(32))  # редакция текста этого разрешения


class TrustedContact(Base):
    """Доверенный человек: узнаёт, что приём не отмечен. Почта и имя — персональные данные третьего лица.

    Письма ему уходят только после его согласия (status = confirmed). Ссылка из письма отдаёт и согласие,
    и отказ, и отписку. Токен ссылки не хранится: это id и подпись HMAC от секретного ключа сайта и nonce,
    поэтому старые ссылки в письмах работают всегда, а смена nonce (новая почта) гасит их все.
    Аккаунт удаляется — удаляется и эта строка.
    status: pending — ждём ответа, confirmed — согласился, declined — отказался, revoked — отписался.
    """

    __tablename__ = "trusted_contacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    nonce: Mapped[str] = mapped_column(String(32))
    consent_version: Mapped[str | None] = mapped_column(String(32))  # какую редакцию текста согласия он принял
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    request_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ScheduleNotified(Base):
    """Какие уведомления по расписанию уже ушли, чтобы не повторять их каждую минуту.

    stage: pre — за N минут, repeat — повтор себе, trusted — письмо доверенному.
    """

    __tablename__ = "schedule_notified"
    __table_args__ = (UniqueConstraint("slot_id", "day", "stage"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    slot_id: Mapped[int] = mapped_column(ForeignKey("schedule_slots.id", ondelete="CASCADE"))
    day: Mapped[date] = mapped_column(Date)
    stage: Mapped[str] = mapped_column(String(16))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class NotificationPrefs(Base):
    """Настройки напоминаний человека: куда слать (почта, Telegram) и о чём.

    Строки нет — напоминания выключены. Telegram привязывается по одноразовой ссылке на бота:
    в базе, как и для писем, хранится только хеш кода из ссылки.
    """

    __tablename__ = "notification_prefs"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    telegram_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    telegram_name: Mapped[str | None] = mapped_column(String(100))   # @username, чтобы показать, куда привязано
    telegram_code_hash: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    telegram_code_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Когда человек дал отдельное согласие на трансграничную передачу данных в Telegram (ст. 12 152-ФЗ).
    telegram_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notify_low: Mapped[bool] = mapped_column(Boolean, default=True)      # «скоро закончится»
    notify_expiry: Mapped[bool] = mapped_column(Boolean, default=True)   # «истекает срок» и «срок истёк»
    expiry_days: Mapped[int] = mapped_column(Integer, default=30)        # за сколько дней предупреждать о сроке


class ReminderSent(Base):
    """Какие напоминания человек уже получил, чтобы не повторять их каждый день.

    kind: low (ref_id — лекарство), expiring и expired (ref_id — упаковка).
    Запись о «low» удаляется, когда остаток пополнили: в следующий раз напомним снова.
    """

    __tablename__ = "reminders_sent"
    __table_args__ = (UniqueConstraint("user_id", "kind", "ref_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    ref_id: Mapped[int] = mapped_column(Integer)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProductCode(Base):
    """Общий справочник «код товара → название». Пополняется, когда кто-то сохраняет лекарство с кодом."""

    __tablename__ = "product_codes"

    gtin: Mapped[str] = mapped_column(String(14), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    form: Mapped[str | None] = mapped_column(String(60))
    dosage: Mapped[str | None] = mapped_column(String(60))
    active_ingredient: Mapped[str | None] = mapped_column(String(200))
    manufacturer: Mapped[str | None] = mapped_column(String(200))
    title: Mapped[str | None] = mapped_column(String(300))          # полное название из аптек
    unit: Mapped[str | None] = mapped_column(String(20))
    pack_size: Mapped[float | None] = mapped_column(Float)          # сколько в упаковке (30 таб)
    blister_size: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(30), default="user")  # user | internet | openfoodfacts
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

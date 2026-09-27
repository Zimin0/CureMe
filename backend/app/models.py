from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint,
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    memberships: Mapped[list["Membership"]] = relationship(back_populates="user", cascade="all, delete-orphan")


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

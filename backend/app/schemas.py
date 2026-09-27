from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

MAX_CATEGORIES = 3  # сколько категорий можно поставить одному лекарству


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- аккаунты и семьи ---
class RegisterIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=6, max_length=128)
    invite_code: str | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(ORM):
    id: int
    email: str
    name: str


class FamilyBrief(BaseModel):
    id: int
    name: str
    role: str


class MeOut(UserOut):
    is_admin: bool = False
    families: list[FamilyBrief]


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: MeOut


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    password: str | None = Field(default=None, min_length=6, max_length=128)


class FamilyIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class MemberOut(BaseModel):
    user_id: int
    name: str
    email: str
    role: str
    joined_at: datetime


class FamilyOut(BaseModel):
    id: int
    name: str
    invite_code: str
    role: str
    members: list[MemberOut]


class AddMemberIn(BaseModel):
    email: EmailStr


class RoleIn(BaseModel):
    role: str = Field(pattern="^(owner|member)$")


class JoinIn(BaseModel):
    code: str


class InviteInfo(BaseModel):
    family_name: str
    members: int


# --- категории ---
class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    icon: str = Field(default="💊", min_length=1, max_length=16)   # эмодзи (с модификаторами бывает до 7 символов)
    color: str = Field(default="#0f9d8a", pattern="^#[0-9a-fA-F]{6}$")


class CategoryOrderIn(BaseModel):
    ids: list[int]


class IndicationHintsIn(BaseModel):
    hints: list[str] = Field(max_length=50)

    @field_validator("hints")
    @classmethod
    def clean(cls, v: list[str]) -> list[str]:
        """Убирает пустые строки и повторы (без учёта регистра), порядок сохраняет."""
        out: list[str] = []
        for h in (" ".join(x.split()) for x in v):
            if len(h) > 60:
                raise ValueError(f"Подсказка длиннее 60 символов: «{h[:20]}…»")
            if h and h.lower() not in {o.lower() for o in out}:
                out.append(h)
        return out


class CategoryOut(ORM):
    id: int
    name: str
    icon: str
    color: str
    medicine_count: int = 0


# --- администрирование ---
class AdminStats(BaseModel):
    users: int
    admins: int
    families: int
    medicines: int
    categories: int


class AdminUserOut(BaseModel):
    id: int
    email: str
    name: str
    is_admin: bool
    created_at: datetime
    families: list[FamilyBrief]


class AdminUserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None
    is_admin: bool | None = None
    password: str | None = Field(default=None, min_length=6, max_length=128)


class AdminFamilyOut(BaseModel):
    id: int
    name: str
    invite_code: str
    created_at: datetime
    medicine_count: int
    members: list[MemberOut]


class AdminMemberIn(BaseModel):
    email: EmailStr
    role: str = Field(default="member", pattern="^(owner|member)$")


# --- лекарства и упаковки ---
class PackageIn(BaseModel):
    quantity: float = Field(default=1, ge=0)
    expiry_date: date | None = None
    opened_at: date | None = None
    serial: str | None = None
    batch: str | None = None
    location: str | None = None


class PackageUpdate(BaseModel):
    quantity: float | None = Field(default=None, ge=0)
    expiry_date: date | None = None
    opened_at: date | None = None
    location: str | None = None
    batch: str | None = None


class PackageOut(ORM):
    id: int
    quantity: float
    expiry_date: date | None
    opened_at: date | None
    serial: str | None
    batch: str | None
    location: str | None
    added_at: datetime
    expired: bool = False
    days_left: int | None = None


def _legacy_category_id(data):
    """Старые версии приложения (закэшированные на телефоне) присылают одну category_id."""
    if isinstance(data, dict) and "category_id" in data and "category_ids" not in data:
        data = {**data, "category_ids": [data["category_id"]] if data["category_id"] is not None else []}
    return data


class MedicineBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category_ids: list[int] = Field(default_factory=list, max_length=MAX_CATEGORIES)  # первая — основная
    form: str | None = None
    dosage: str | None = None
    active_ingredient: str | None = None
    manufacturer: str | None = None
    indications: str = ""
    contraindications: str = ""
    notes: str = ""
    unit: str = "шт"
    min_quantity: float | None = Field(default=None, ge=0)
    blister_size: int | None = Field(default=None, ge=1, le=1000)
    gtin: str | None = None


class MedicineIn(MedicineBase):
    packages: list[PackageIn] = []

    @model_validator(mode="before")
    @classmethod
    def _legacy(cls, data):
        return _legacy_category_id(data)


class MedicineUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category_ids: list[int] | None = Field(default=None, max_length=MAX_CATEGORIES)
    form: str | None = None
    dosage: str | None = None
    active_ingredient: str | None = None
    manufacturer: str | None = None
    indications: str | None = None
    contraindications: str | None = None
    notes: str | None = None
    unit: str | None = None
    min_quantity: float | None = None
    blister_size: int | None = None
    gtin: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _legacy(cls, data):
        return _legacy_category_id(data)


class MarkIn(BaseModel):
    is_favorite: bool | None = None
    helps_me: bool | None = None
    personal_note: str | None = None


class StockOut(BaseModel):
    total: float                 # в годных упаковках
    expired_quantity: float
    package_count: int
    nearest_expiry: date | None
    days_left: int | None
    status: str                  # ok | low | out | expiring | expired


class MedicineOut(MedicineBase):
    id: int
    categories: list[CategoryOut]
    category: CategoryOut | None  # основная (первая) категория — для значка и цвета
    stock: StockOut
    is_favorite: bool
    helps_me: bool
    personal_note: str
    helps_members: list[str]     # кому ещё из семьи помогает
    photo_url: str | None
    created_at: datetime
    updated_at: datetime


class MedicineDetail(MedicineOut):
    packages: list[PackageOut]


class ConsumeIn(BaseModel):
    amount: float = Field(default=1, gt=0)


class SuggestionOut(BaseModel):
    medicine: MedicineOut
    score: float
    reasons: list[str]
    warnings: list[str]


class SuggestOut(BaseModel):
    query: str
    results: list[SuggestionOut]
    disclaimer: str


# --- сканирование ---
class ScanIn(BaseModel):
    raw: str = Field(min_length=1, max_length=512)


class ProductInfo(ORM):
    gtin: str
    name: str
    title: str | None = None
    form: str | None = None
    dosage: str | None = None
    active_ingredient: str | None = None
    manufacturer: str | None = None
    unit: str | None = None
    pack_size: float | None = None
    blister_size: int | None = None
    source: str                        # user | internet | openfoodfacts


class ScanOut(BaseModel):
    parsed: dict
    display_code: str | None
    medicine: MedicineOut | None       # такое лекарство уже есть в аптечке
    product: ProductInfo | None        # подсказка названия для нового лекарства
    duplicate_package: bool            # эту же упаковку уже сканировали


# --- главная ---
class OverviewOut(BaseModel):
    total_medicines: int
    total_packages: int
    expired: list[MedicineOut]
    expiring: list[MedicineOut]
    low: list[MedicineOut]
    favorites: list[MedicineOut]
    helps_me: list[MedicineOut]
    expiring_soon_days: int

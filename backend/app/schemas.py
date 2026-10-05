import re
import unicodedata
from datetime import date, datetime

from typing import Literal, Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from .security import MAX_PASSWORD_BYTES

MAX_CATEGORIES = 3  # сколько категорий можно поставить одному лекарству
TEXT_MAX = 5000     # длинные текстовые поля: показания, заметки
COMMENT_MAX = 1000  # комментарий к приёму лекарства


def _password_bytes(value: str) -> str:
    if len(value.encode()) > MAX_PASSWORD_BYTES:
        raise ValueError(
            f"Пароль слишком длинный: не больше {MAX_PASSWORD_BYTES} байт "
            "(примерно 36 русских или 72 латинских символа)"
        )
    return value


# Самые частые пароли и «клавиатурные» ряды: их подбирают первыми, поэтому и длинным (12+) такие не принимаем.
COMMON_PASSWORDS = {
    "123456789012", "1234567890123", "qwertyuiop12", "qwertyuiopas", "qwerty123456", "password1234", "password12345",
    "123456123456", "111111111111", "000000000000", "йцукенгшщзхъ", "qwertyqwerty", "1q2w3e4r5t6y", "iloveyou1234",
    "zxcvbnm12345", "asdfghjkl123", "kapsulka1234", "kapsulka12345",
}
MIN_PASSWORD = 12
MIN_ADMIN_PASSWORD = 16


def _strong_password(value: str) -> str:
    _password_bytes(value)
    if value.isdigit() or len(set(value)) < 4 or value.lower() in COMMON_PASSWORDS:
        raise ValueError("Слишком простой пароль: придумайте фразу из нескольких слов, не меньше 12 символов")
    return value


# Новый пароль: от 12 символов, не из одних цифр и не из частых, и не длиннее, чем умеет bcrypt.
# Администраторам при смене нужно не меньше 16 символов (проверяется там, где пароль меняют).
NewPassword = Annotated[str, Field(min_length=MIN_PASSWORD, max_length=128), AfterValidator(_strong_password)]
# Старые пароли бывали и по 6 символов, поэтому при входе длину снизу не проверяем.
AnyPassword = Annotated[str, Field(min_length=1, max_length=128)]


# Имя человека попадает в письма незнакомым людям («доверенный человек») и в жёлтые плашки других семей.
# Ссылку в нём не пропускаем: иначе наша почта работала бы на рассылку чужих ссылок.
_LINK_IN_NAME = re.compile(r"(?i)(https?://|www\.|\w\.(?:ru|com|net|org|info|xyz|top|site|online|su|рф|me|io|cc|ly)\b)")
_BIDI = set("\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")


def _plain_name(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Укажите имя")
    if any(unicodedata.category(c) in ("Cc", "Zl", "Zp") or c in _BIDI for c in value):
        raise ValueError("В имени не должно быть переводов строки и управляющих символов")
    if _LINK_IN_NAME.search(value):
        raise ValueError("В имени не должно быть ссылки или адреса сайта")
    return value


PersonName = Annotated[str, Field(min_length=1, max_length=100), AfterValidator(_plain_name)]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- аккаунты и семьи ---
class RegisterIn(BaseModel):
    email: EmailStr
    name: PersonName
    password: NewPassword
    invite_code: str | None = Field(default=None, max_length=32)
    consent: bool = False  # галочка «даю согласие на обработку персональных данных»


class PasswordResetRequestIn(BaseModel):
    email: EmailStr


class PasswordResetConfirmIn(BaseModel):
    email: EmailStr
    code: str = Field(min_length=8, max_length=8, pattern=r"^\d{8}$")
    password: NewPassword


class ConsentIn(BaseModel):
    consent: bool


class DeleteAccountIn(BaseModel):
    password: AnyPassword


class LoginIn(BaseModel):
    email: EmailStr
    password: AnyPassword


class UserOut(ORM):
    id: int
    email: str
    name: str


class FamilyBrief(BaseModel):
    id: int
    name: str
    role: str
    status: str = "active"  # active | frozen: замороженная аптечка открыта только на чтение и выгрузку (R14)


class PlusEndingOut(BaseModel):
    """Баннер вверху приложения: Плюс семьи заканчивается или закончился, идёт срок выбора состава (R13)."""

    state: str  # ending | ended
    date: datetime  # конец Плюса или последний день выбора
    is_owner: bool
    people_limit: int


class MeOut(UserOut):
    is_admin: bool = False
    consent_needed: bool = False  # согласия нет или оно старой редакции — показать экран согласия
    access_blocked: bool = False  # закрытый режим, а этого аккаунта нет в списке тестировщиков
    email_verified: bool = False
    verification_needed: bool = False  # почта не подтверждена, а проверка включена — показать экран «Проверьте почту»
    families: list[FamilyBrief]
    owner_transfer_waiting: bool = False  # кому-то из семьи нужен ответ этого человека по передаче владения (R23)
    plus_ending: PlusEndingOut | None = None
    # Сколько ещё своих аптечек можно создать: None — без ограничений (Плюс или платная версия выключена).
    own_families_left: int | None = None
    next_change_at: datetime | None = None  # до этого момента сменить семью нельзя (кулдаун, R11)
    plus_active: bool = False  # у аккаунта оплачен Плюс (нужно, чтобы отличить «лимит бесплатной» от «потолка Плюса»)
    # Только после смены своего пароля: старый токен уже не действует, вот новый.
    access_token: str | None = None


class AccessOut(BaseModel):
    closed: bool
    telegram: bool = False  # Telegram на сайте включён (бот настроен и переключатель в админке)
    debug: bool = False  # режим отладки: показывать версию приложения на каждой странице
    # Для приветственной страницы гостей: пробный Плюс и (если задана и платная версия включена) цена.
    trial_days: int = 0
    price_month: int | None = None
    price_year: int | None = None
    # Для публичной страницы /plus: цена тарифа как её задал администратор, даже пока платная версия выключена.
    billing_enabled: bool = False
    listed_price_month: int | None = None
    listed_price_year: int | None = None


class DebugSettings(BaseModel):
    enabled: bool


class TelegramSettings(BaseModel):
    enabled: bool          # переключатель в админке
    configured: bool = False  # бот настроен в .env (только в ответе админки)


class VerifyEmailIn(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


class AccessSettings(BaseModel):
    closed: bool
    user_ids: list[int] = Field(default_factory=list, max_length=1000)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: MeOut


class UserUpdate(BaseModel):
    name: PersonName | None = None
    password: NewPassword | None = None
    # Чтобы сменить пароль, нужен текущий: иначе украденный токен позволил бы захватить аккаунт навсегда.
    current_password: AnyPassword | None = None


class FamilyIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class MemberOut(BaseModel):
    user_id: int
    name: str
    email: str
    role: str
    is_owner: bool = False  # владелец семьи: приглашает и платит (R02)
    joined_at: datetime


class OwnerTransferOut(BaseModel):
    """Незавершённая передача владения (R23): кто кому предложил и до когда ждём ответа."""
    kind: str  # offer: владелец предлагает; request: участник просит «Хочу оплачивать»
    from_user_id: int | None = None
    from_name: str = ""
    to_user_id: int | None = None
    to_name: str = ""
    expires_at: datetime
    can_answer: bool = False  # смотрящий может принять или отказаться
    can_withdraw: bool = False  # смотрящий может забрать своё предложение


class FamilyOut(BaseModel):
    id: int
    name: str
    invite_code: str | None = None  # только у владельца: одноразовый код на 24 часа (R04)
    invite_expires_at: datetime | None = None
    role: str
    members: list[MemberOut]
    owner_transfer: OwnerTransferOut | None = None
    next_transfer_at: datetime | None = None  # пока не наступило, владение передать нельзя (кулдаун 7 дней, R23)
    status: str = "active"


class OwnerOfferIn(BaseModel):
    user_id: int


class CompressIn(BaseModel):
    """Выбор владельца после окончания Плюса (R13): кто остаётся (кроме него самого) и какие аптечки остаются активными."""

    keep_user_ids: list[int] = []
    keep_cabinet_ids: list[int] = []  # пусто: самые давние


class CompressionSettingsIO(BaseModel):
    enabled: bool = False


class RoleIn(BaseModel):  # используется админкой (инструмент поддержки)
    role: str = Field(pattern="^(owner|member)$")


class JoinIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    carry_plus: bool = False  # у человека оплачен Плюс: перенести оставшиеся дни в семью (R08 «а»)


class InviteInfo(BaseModel):
    family_name: str
    owner_name: str
    full: bool = False  # в бесплатной семье уже предел участников: вступить не получится


# --- категории ---
class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    icon: str = Field(default="💊", min_length=1, max_length=16)   # эмодзи (с модификаторами бывает до 7 символов)
    color: str = Field(default="#0f9d8a", pattern="^#[0-9a-fA-F]{6}$")


class CategoryOrderIn(BaseModel):
    ids: list[int] = Field(max_length=1000)


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
    email_verified: bool
    created_at: datetime
    families: list[FamilyBrief]
    plan: str = "free"
    plus_until: datetime | None = None
    plus_active: bool = False  # Плюс аккаунта оплачен и не истёк
    auto_renew: bool = False  # включено автопродление (способ оплаты сохранён в ЮKassa)
    household_id: int | None = None
    is_owner: bool = False  # владелец своей семьи: платит и приглашает


class HouseholdEventOut(BaseModel):
    id: int
    kind: str
    user_id: int | None = None
    actor_id: int | None = None
    detail: str = ""
    created_at: datetime


class AdminUserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None
    is_admin: bool | None = None
    # Подтвердить почту за человека, например если письмо не доходит.
    email_verified: bool | None = None
    password: NewPassword | None = None


class AdminFamilyOut(BaseModel):
    id: int
    name: str
    created_at: datetime
    medicine_count: int
    members: list[MemberOut]
    # Тариф семьи, которой принадлежит аптечка (только для чтения: менять нужно у человека семьи).
    plan: str = "free"
    plus_until: datetime | None = None
    plus_active: bool = False  # Плюс оплачен и не истёк
    owner_id: int | None = None
    owner_name: str | None = None
    household_id: int | None = None
    household_people: int = 0
    household_cabinets: int = 0


# --- тарифы (plans.py) ---
class BillingSettings(BaseModel):
    enabled: bool = False  # платная версия включена: у семей без Плюса действуют лимиты
    # Стоимость Плюса для аккаунта в рублях; пусто — цена не показывается.
    price_month: int | None = Field(default=None, ge=1, le=100_000)
    price_year: int | None = Field(default=None, ge=1, le=1_000_000)
    # Сколько дней Плюса дарим при первом подтверждении почты; 0 — пробный период выключен.
    trial_days: int = Field(default=5, ge=0, le=90)
    # Сиреневый вид интерфейса у пользователей с Плюсом; выключено — у всех прежний зелёный.
    plus_theme: bool = True


class AdminPlanIn(BaseModel):
    plan: str = Field(pattern="^(free|plus)$")
    plus_until: datetime | None = None  # пусто — Плюс бессрочно


class PlanFeatureOut(BaseModel):
    key: str
    title: str
    description: str
    available: bool


class PlanOut(BaseModel):
    plan: str                          # free | plus — что записано у аккаунта главного владельца семьи
    owner_name: str | None = None      # чей это Плюс: имя главного владельца семьи
    plus_until: datetime | None        # до какого момента Плюс; пусто — бессрочно
    plus_active: bool                  # Плюс оплачен и не истёк
    billing_enabled: bool              # платная версия включена администратором
    plus_theme: bool = True            # у людей с Плюсом интерфейс сиреневый (переключатель в админке «Тарифы»)
    price_month: int | None = None     # стоимость Плюса в рублях за месяц / за год (настраивает админ)
    price_year: int | None = None
    has_plus: bool                     # семье доступно всё из Плюса (Плюс или платная версия выключена)
    limits: dict[str, int | None]      # действующие лимиты семьи; None — без ограничений
    free_limits: dict[str, int]        # лимиты бесплатной версии — для сравнения на странице «Плюс»
    usage: dict[str, int]              # сколько уже есть: members, medicines
    features: list[PlanFeatureOut]


class AdminMemberIn(BaseModel):
    email: EmailStr
    role: str = Field(default="member", pattern="^(owner|member)$")


# --- лекарства и упаковки ---
class PackageIn(BaseModel):
    quantity: float = Field(default=1, ge=0, le=1_000_000)
    expiry_date: date | None = None
    opened_at: date | None = None
    serial: str | None = Field(default=None, max_length=64)
    batch: str | None = Field(default=None, max_length=64)
    location: str | None = Field(default=None, max_length=100)


class PackageUpdate(BaseModel):
    quantity: float | None = Field(default=None, ge=0, le=1_000_000)
    expiry_date: date | None = None
    opened_at: date | None = None
    location: str | None = Field(default=None, max_length=100)
    batch: str | None = Field(default=None, max_length=64)


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
    # Длины как у столбцов в базе: Postgres на более длинной строке падает с ошибкой 500.
    form: str | None = Field(default=None, max_length=60)
    dosage: str | None = Field(default=None, max_length=60)
    active_ingredient: str | None = Field(default=None, max_length=200)
    manufacturer: str | None = Field(default=None, max_length=200)
    indications: str = Field(default="", max_length=TEXT_MAX)
    contraindications: str = Field(default="", max_length=TEXT_MAX)
    notes: str = Field(default="", max_length=TEXT_MAX)
    unit: str = Field(default="шт", min_length=1, max_length=20)
    min_quantity: float | None = Field(default=None, ge=0, le=1_000_000)
    blister_size: int | None = Field(default=None, ge=1, le=1000)
    gtin: str | None = Field(default=None, max_length=512)


class MedicineIn(MedicineBase):
    packages: list[PackageIn] = Field(default_factory=list, max_length=100)

    @model_validator(mode="before")
    @classmethod
    def _legacy(cls, data):
        return _legacy_category_id(data)


class MedicineUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category_ids: list[int] | None = Field(default=None, max_length=MAX_CATEGORIES)
    form: str | None = Field(default=None, max_length=60)
    dosage: str | None = Field(default=None, max_length=60)
    active_ingredient: str | None = Field(default=None, max_length=200)
    manufacturer: str | None = Field(default=None, max_length=200)
    indications: str | None = Field(default=None, max_length=TEXT_MAX)
    contraindications: str | None = Field(default=None, max_length=TEXT_MAX)
    notes: str | None = Field(default=None, max_length=TEXT_MAX)
    unit: str | None = Field(default=None, min_length=1, max_length=20)
    min_quantity: float | None = Field(default=None, ge=0, le=1_000_000)
    blister_size: int | None = Field(default=None, ge=1, le=1000)
    gtin: str | None = Field(default=None, max_length=512)
    # Где лежит: круг на схеме полок (доли 0..1). null во всех трёх — «убрать метку».
    place_x: float | None = Field(default=None, ge=0, le=1)
    place_y: float | None = Field(default=None, ge=0, le=1)
    place_r: float | None = Field(default=None, ge=0.01, le=0.5)

    @model_validator(mode="before")
    @classmethod
    def _legacy(cls, data):
        return _legacy_category_id(data)


class Shelf(BaseModel):
    id: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(default="", max_length=60)
    kind: Literal["shelf", "box"] = "shelf"  # полка или контейнер, который стоит на полке
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(gt=0, le=1)
    h: float = Field(gt=0, le=1)


class ShelfPlan(BaseModel):
    """Схема аптечки: прямоугольники полок и ящиков в долях от 0 до 1 (ширина и высота схемы)."""

    shelves: list[Shelf] = Field(default_factory=list, max_length=30)
    height: float = Field(default=1.0, gt=0, le=3)  # высота схемы в долях ширины


class MarkIn(BaseModel):
    is_favorite: bool | None = None
    helps_me: bool | None = None
    personal_note: str | None = Field(default=None, max_length=TEXT_MAX)


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
    place_x: float | None = None
    place_y: float | None = None
    place_r: float | None = None
    created_at: datetime
    updated_at: datetime
    # Заполняются только в поиске по всем аптечкам семьи (R05): из какой аптечки лекарство.
    family_id: int | None = None
    family_name: str | None = None


class MedicineDetail(MedicineOut):
    packages: list[PackageOut]


class MoveIn(BaseModel):
    """Перенос лекарств в другую аптечку той же семьи (R17)."""

    to_family_id: int
    medicine_ids: list[int] = Field(min_length=1, max_length=500)


class MoveOut(BaseModel):
    moved: int    # перенесено карточек
    merged: int   # из них слито с такими же по штрихкоду
    to_family_id: int


class SplitIn(BaseModel):
    """Разделение аптечки: выбранные лекарства уходят в новую аптечку (R18)."""

    name: str = Field(min_length=1, max_length=100)
    medicine_ids: list[int] = Field(min_length=1, max_length=500)


class ConsumeIn(BaseModel):
    amount: float = Field(default=1, gt=0, le=1_000_000)
    comment: str = Field(default="", max_length=COMMENT_MAX)  # необязательно: «почему принял»


class IntakeOut(BaseModel):
    id: int
    medicine_id: int | None       # None — лекарство уже удалили из аптечки
    medicine_name: str
    unit: str
    user_id: int
    user_name: str
    mine: bool
    amount: float
    comment: str                  # только свои; у чужих записей пусто
    taken_at: datetime
    last_at: datetime


class IntakeUpdate(BaseModel):
    comment: str = Field(max_length=COMMENT_MAX)


class OlderHistoryOut(BaseModel):
    history_since: datetime | None  # с какого момента видна история; None — вся (Плюс)
    hidden: int                     # сколько более ранних записей скрыто до подключения Плюса


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


# --- напоминания ---
class NotificationPrefsOut(BaseModel):
    available: bool                 # есть ли у человека семья с Плюсом
    email: str
    email_possible: bool            # на сайте настроена почта, и адрес подтверждён
    telegram_possible: bool         # на сайте настроен Telegram-бот
    telegram_bot: str | None
    email_enabled: bool
    telegram_enabled: bool
    telegram_connected: bool
    telegram_name: str | None
    notify_low: bool
    notify_expiry: bool
    notify_expired: bool
    expiry_days: int


class NotificationPrefsIn(BaseModel):
    email_enabled: bool | None = None
    telegram_enabled: bool | None = None
    notify_low: bool | None = None
    notify_expiry: bool | None = None
    notify_expired: bool | None = None
    expiry_days: int | None = Field(default=None, ge=1, le=180)

    @model_validator(mode="after")
    def no_nulls(self):
        for k in self.model_fields_set:
            if getattr(self, k) is None:
                raise ValueError(f"{k}: нужно значение")
        return self


class TelegramLinkIn(BaseModel):
    # Отдельное согласие на трансграничную передачу: Telegram — иностранная компания.
    consent: bool


class TelegramLinkOut(BaseModel):
    url: str
    ttl_minutes: int


# --- расписание приёма ---
MAX_TIMES = 12          # приёмов в день у одного назначения
MAX_SCHEDULES = 100     # назначений у одного человека


def _check_days(days: list[int]) -> list[int]:
    if any(d < 0 or d > 6 for d in days):
        raise ValueError("День недели — число от 0 (понедельник) до 6 (воскресенье)")
    return sorted(set(days))


def _check_times(times: list[int]) -> list[int]:
    if any(t < 0 or t > 1439 for t in times):
        raise ValueError("Время — число минут от полуночи, от 0 до 1439")
    return sorted(set(times))


class SlotOut(BaseModel):
    id: int
    weekday: int                  # 0 — понедельник
    minute: int                   # минут от полуночи по Москве


class ScheduleOut(BaseModel):
    id: int
    medicine_id: int | None       # None — лекарство уже удалили из аптечки
    medicine_name: str
    unit: str
    amount: float
    start_date: date
    end_date: date | None
    every_weeks: int
    slots: list[SlotOut]


class ScheduleCreate(BaseModel):
    """Дни × время: «пн, ср, пт» и «08:00, 20:00» дают шесть приёмов в неделю."""

    medicine_id: int
    amount: float = Field(default=1, gt=0, le=1_000_000)
    days: list[int] = Field(default=list(range(7)), min_length=1, max_length=7)  # по умолчанию — каждый день
    times: list[int] = Field(min_length=1, max_length=MAX_TIMES)
    start_date: date | None = None                                              # по умолчанию — сегодня
    end_date: date | None = None
    every_weeks: int = Field(default=1, ge=1, le=12)

    _days = field_validator("days")(_check_days)
    _times = field_validator("times")(_check_times)

    @model_validator(mode="after")
    def _dates(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("Дата окончания раньше даты начала")
        return self


class ScheduleUpdate(BaseModel):
    amount: float | None = Field(default=None, gt=0, le=1_000_000)
    start_date: date | None = None
    end_date: date | None = None
    every_weeks: int | None = Field(default=None, ge=1, le=12)


class SlotsIn(BaseModel):
    """Добавить приёмы (дни × время) к существующему назначению."""

    days: list[int] = Field(min_length=1, max_length=7)
    times: list[int] = Field(min_length=1, max_length=MAX_TIMES)

    _days = field_validator("days")(_check_days)
    _times = field_validator("times")(_check_times)


class SlotsRemove(BaseModel):
    """Убрать приёмы серией: все, что попадают на выбранные дни и время.

    Пустой days — любой день, пустой times — любое время. «Больше не пью по вторникам в 16:00» —
    это days=[1], times=[960]; «совсем не пью по вторникам» — days=[1], times=[].
    """

    days: list[int] = Field(default_factory=list, max_length=7)
    times: list[int] = Field(default_factory=list, max_length=24 * 60)

    _days = field_validator("days")(_check_days)
    _times = field_validator("times")(_check_times)


class SlotMove(BaseModel):
    """Перетащить один приём на другой день и/или время."""

    weekday: int | None = Field(default=None, ge=0, le=6)
    minute: int | None = Field(default=None, ge=0, le=1439)


class OccurrenceOut(BaseModel):
    """Конкретный приём на конкретную дату и отметка, принят ли он (по истории приёма)."""

    schedule_id: int
    slot_id: int
    medicine_id: int | None
    medicine_name: str
    unit: str
    amount: float
    date: date
    minute: int
    taken: bool
    taken_at: datetime | None


# --- уведомления по расписанию и доверенный человек ---
class TrustedOut(BaseModel):
    name: str
    email: str
    status: str                   # pending | confirmed | declined | revoked
    confirmed_at: datetime | None


class SchedulePrefsOut(BaseModel):
    available: bool               # есть семья с Плюсом (или платная версия выключена)
    email: str
    email_possible: bool          # на сайте настроена почта, адрес подтверждён
    enabled: bool
    lead_minutes: int
    repeat_minutes: int
    escalate_enabled: bool
    escalate_minutes: int
    share_medicine_name: bool
    escalate_consent_at: datetime | None  # когда разрешено сообщать доверенному (None — не разрешено)
    escalate_consent_version: str | None = None
    trusted: TrustedOut | None


class SchedulePrefsIn(BaseModel):
    enabled: bool | None = None
    lead_minutes: int | None = Field(default=None, ge=1, le=120)
    repeat_minutes: int | None = Field(default=None, ge=1, le=60)
    escalate_enabled: bool | None = None
    escalate_minutes: int | None = Field(default=None, ge=1, le=120)
    share_medicine_name: bool | None = None
    # Вместе с escalate_enabled=true: человек разрешает сообщать доверенному, что приём не отмечен.
    escalate_consent: bool | None = None

    @model_validator(mode="after")
    def no_nulls(self):
        for k in self.model_fields_set:
            if getattr(self, k) is None:
                raise ValueError(f"{k}: нужно значение")
        return self


class TrustedIn(BaseModel):
    name: PersonName
    email: EmailStr
    # Человек подтверждает, что сообщил доверенному и тот не против: почта третьего лица — его ответственность.
    attest: bool

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Укажите, как зовут этого человека")
        return v


class TrustedTokenIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class TrustedPublicOut(BaseModel):
    """Что видит доверенный человек на странице по ссылке из письма: только имя того, кто его указал."""

    user_name: str
    status: str


# --- оплата (payments.py) ---
class PayIn(BaseModel):
    period: str = Field(pattern="^(month|year)$")
    auto_renew: bool = False
    agree: bool  # согласие с офертой, условиями и политикой: без него оплата не создаётся

    @model_validator(mode="after")
    def _agreed(self):
        if not self.agree:
            raise ValueError("Нужно согласиться с офертой")
        return self


class PayStarted(BaseModel):
    payment_id: int
    confirmation_url: str  # страница оплаты ЮKassa


class PaymentBrief(BaseModel):
    id: int
    period: str
    amount: int
    status: str
    recurring: bool
    created_at: datetime
    paid_at: datetime | None = None
    receipt_url: str | None = None


class PayStatus(BaseModel):
    enabled: bool  # оплату можно начать
    plus_active: bool
    plus_until: datetime | None = None
    can_pay: bool = False  # этот человек может сейчас оплатить Плюс семье: платит только владелец (R06)
    is_owner: bool = False
    owner_name: str | None = None  # кому платить, если не он сам
    auto_renew: bool
    recurring_enabled: bool = False  # автоплатежи подключены: можно показывать галочку автопродления
    price_month: int | None = None
    price_year: int | None = None
    payments: list[PaymentBrief] = []


class AdminPaymentOut(PaymentBrief):
    email: str
    user_id: int | None = None
    user_name: str | None = None
    receipt_sent_at: datetime | None = None


class ReceiptIn(BaseModel):
    url: str = Field(min_length=10, max_length=500, pattern=r"^https://\S+$")
    send_email: bool = True

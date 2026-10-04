from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .config import get_settings
from .models import AppSetting, Family, Intake, Medicine, MedicineCategory, Membership, Package, UserMark
from .schemas import CategoryOut, IntakeOut, MedicineDetail, MedicineOut, PackageOut, StockOut
from .seed import DEFAULT_INDICATION_HINTS

INDICATION_HINTS = "indication_hints"
ACCESS = "access"
DEBUG_MODE = "debug_mode"
TELEGRAM_SWITCH = "telegram_switch"


def telegram_switch_on(db: Session) -> bool:
    """Переключатель «Telegram включён» в админке. По умолчанию выключен: Telegram на сайте скрыт."""
    row = db.get(AppSetting, TELEGRAM_SWITCH)
    return bool(row.value.get("enabled")) if row else False


def set_telegram_switch(db: Session, enabled: bool) -> bool:
    row = db.get(AppSetting, TELEGRAM_SWITCH)
    if row:
        row.value = {"enabled": enabled}
    else:
        db.add(AppSetting(key=TELEGRAM_SWITCH, value={"enabled": enabled}))
    db.commit()
    return enabled


def telegram_active(db: Session) -> bool:
    """Telegram работает, только если и бот настроен в .env, и админ включил переключатель."""
    return get_settings().telegram_enabled and telegram_switch_on(db)


def debug_enabled(db: Session) -> bool:
    """Режим отладки: на каждой странице показывается версия приложения. По умолчанию выключен."""
    row = db.get(AppSetting, DEBUG_MODE)
    return bool(row.value.get("enabled")) if row else False


def set_debug_enabled(db: Session, enabled: bool) -> bool:
    row = db.get(AppSetting, DEBUG_MODE)
    if row:
        row.value = {"enabled": enabled}
    else:
        db.add(AppSetting(key=DEBUG_MODE, value={"enabled": enabled}))
    db.commit()
    return enabled


def access_settings(db: Session) -> dict:
    """Закрытый режим: {"closed": bool, "user_ids": [...]}. По умолчанию сайт открыт для всех."""
    row = db.get(AppSetting, ACCESS)
    value = row.value if row else {}
    return {"closed": bool(value.get("closed")), "user_ids": [int(i) for i in value.get("user_ids", [])]}


def set_access_settings(db: Session, closed: bool, user_ids: list[int]) -> dict:
    value = {"closed": closed, "user_ids": sorted(set(user_ids))}
    row = db.get(AppSetting, ACCESS)
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=ACCESS, value=value))
    db.commit()
    return value


def has_access(db: Session, user) -> bool:
    """В закрытом режиме пользоваться сайтом могут только администраторы и отмеченные ими аккаунты."""
    acc = access_settings(db)
    return not acc["closed"] or user.is_admin or user.id in acc["user_ids"]


def indication_hints(db: Session) -> list[str]:
    row = db.get(AppSetting, INDICATION_HINTS)
    return list(row.value) if row else list(DEFAULT_INDICATION_HINTS)


def set_indication_hints(db: Session, hints: list[str]) -> list[str]:
    row = db.get(AppSetting, INDICATION_HINTS)
    if row:
        row.value = hints
    else:
        db.add(AppSetting(key=INDICATION_HINTS, value=hints))
    db.commit()
    return hints


FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def spreadsheet_safe(value):
    """Текст для CSV, который Excel и Google Таблицы приняли бы за формулу, получает апостроф впереди.

    Название лекарства или заметку может написать любой человек семьи; без этого «=HYPERLINK(...)» в названии
    выполнилась бы у того, кто откроет выгрузку в Excel (CSV injection). Числа и даты не трогаем.
    """
    return "'" + value if isinstance(value, str) and value.startswith(FORMULA_START) else value


def stock_of(med: Medicine, today: date | None = None) -> StockOut:
    today = today or date.today()
    soon = get_settings().expiring_soon_days
    good = [p for p in med.packages if not (p.expiry_date and p.expiry_date < today) and p.quantity > 0]
    expired = [p for p in med.packages if p.expiry_date and p.expiry_date < today and p.quantity > 0]
    total = sum(p.quantity for p in good)
    nearest = min((p.expiry_date for p in good if p.expiry_date), default=None)
    days_left = (nearest - today).days if nearest else None

    if expired:
        status = "expired"
    elif total <= 0:
        status = "out"
    elif days_left is not None and days_left <= soon:
        status = "expiring"
    elif med.min_quantity is not None and total <= med.min_quantity:
        status = "low"
    else:
        status = "ok"
    return StockOut(
        total=round(total, 2),
        expired_quantity=round(sum(p.quantity for p in expired), 2),
        package_count=len(good) + len(expired),
        nearest_expiry=nearest,
        days_left=days_left,
        status=status,
    )


def load_medicines(db: Session, family_id: int, ids: list[int] | None = None) -> list[Medicine]:
    q = (
        select(Medicine)
        .where(Medicine.family_id == family_id)
        .options(
            selectinload(Medicine.packages),
            selectinload(Medicine.category_links).joinedload(MedicineCategory.category),
            selectinload(Medicine.marks),
        )
        .order_by(Medicine.name)
    )
    if ids is not None:
        q = q.where(Medicine.id.in_(ids))
    return list(db.scalars(q))


def load_household_medicines(db: Session, fam: Family) -> list[tuple[Family, Medicine]]:
    """Лекарства всех активных аптечек семьи (поиск и подбор по всем аптечкам, R05). Замороженные не участвуют."""
    cabinets = [c for c in (fam.household.cabinets if fam.household else [fam]) if c.status != "frozen"]
    return [(c, m) for c in sorted(cabinets, key=lambda c: c.id) for m in load_medicines(db, c.id)]


def member_names(db: Session, family_id: int) -> dict[int, str]:
    rows = db.scalars(
        select(Membership).where(Membership.family_id == family_id).options(selectinload(Membership.user))
    )
    return {m.user_id: m.user.name for m in rows}


def medicine_out(med: Medicine, user_id: int, names: dict[int, str], detail: bool = False) -> MedicineOut:
    mine: UserMark | None = next((m for m in med.marks if m.user_id == user_id), None)
    data = dict(
        id=med.id, name=med.name, category_ids=[c.id for c in med.categories], form=med.form, dosage=med.dosage,
        active_ingredient=med.active_ingredient, manufacturer=med.manufacturer,
        indications=med.indications, contraindications=med.contraindications, notes=med.notes,
        unit=med.unit, min_quantity=med.min_quantity, blister_size=med.blister_size, gtin=med.gtin,
        categories=[CategoryOut.model_validate(c) for c in med.categories],
        category=CategoryOut.model_validate(med.category) if med.category else None,
        stock=stock_of(med),
        is_favorite=bool(mine and mine.is_favorite),
        helps_me=bool(mine and mine.helps_me),
        personal_note=mine.personal_note if mine else "",
        helps_members=[names[m.user_id] for m in med.marks if m.helps_me and m.user_id != user_id and m.user_id in names],
        photo_url=f"/api/media/{med.photo}" if med.photo else None,
        created_at=med.created_at, updated_at=med.updated_at,
    )
    if not detail:
        return MedicineOut(**data)
    today = date.today()
    pkgs = [
        PackageOut.model_validate(p).model_copy(update={
            "expired": bool(p.expiry_date and p.expiry_date < today),
            "days_left": (p.expiry_date - today).days if p.expiry_date else None,
        })
        for p in med.packages
    ]
    return MedicineDetail(**data, packages=pkgs)


def consume(med: Medicine, amount: float) -> float:
    """Списывает из годных упаковок, начиная с той, что истекает раньше. Возвращает недостачу."""
    today = date.today()
    usable = sorted(
        (p for p in med.packages if p.quantity > 0 and not (p.expiry_date and p.expiry_date < today)),
        key=lambda p: (p.expiry_date is None, p.expiry_date or date.max, p.id),
    )
    left = amount
    for p in usable:
        take = min(p.quantity, left)
        p.quantity = round(p.quantity - take, 4)
        if p.opened_at is None:
            p.opened_at = today
        left -= take
        if left <= 0:
            break
    return max(left, 0)


MERGE_WINDOW = timedelta(minutes=1)


def _aware(dt: datetime) -> datetime:
    """SQLite отдаёт время без часового пояса; у нас везде UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def record_intake(
    db: Session, med: Medicine, user_id: int, amount: float, comment: str = "", now: datetime | None = None
) -> Intake:
    """Пишет приём в историю. Если тот же человек нажал «Принял» у этого лекарства меньше минуты
    назад (считая от последнего нажатия), дописывает количество в ту же запись."""
    now = now or datetime.now(timezone.utc)
    comment = comment.strip()
    last = db.scalar(
        select(Intake).where(Intake.medicine_id == med.id, Intake.user_id == user_id)
        .order_by(Intake.last_at.desc(), Intake.id.desc()).limit(1)
    )
    if last and now - _aware(last.last_at) <= MERGE_WINDOW:
        last.amount = round(last.amount + amount, 4)
        last.last_at = now
        if comment:
            last.comment = f"{last.comment}\n{comment}" if last.comment else comment
        return last
    intake = Intake(
        family_id=med.family_id, medicine_id=med.id, medicine_name=med.name, unit=med.unit,
        user_id=user_id, amount=round(amount, 4), comment=comment, taken_at=now, last_at=now,
    )
    db.add(intake)
    return intake


def intake_out(i: Intake, user_id: int, names: dict[int, str]) -> IntakeOut:
    mine = i.user_id == user_id
    return IntakeOut(
        id=i.id, medicine_id=i.medicine_id, medicine_name=i.medicine_name, unit=i.unit,
        user_id=i.user_id, user_name=names.get(i.user_id) or i.user.name, mine=mine,
        amount=i.amount, comment=i.comment if mine else "",
        taken_at=_aware(i.taken_at), last_at=_aware(i.last_at),
    )


def find_package_by_serial(db: Session, family_id: int, gtin: str, serial: str) -> Package | None:
    return db.scalar(
        select(Package).join(Medicine)
        .where(Medicine.family_id == family_id, Medicine.gtin == gtin, Package.serial == serial)
    )

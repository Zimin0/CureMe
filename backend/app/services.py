from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .config import get_settings
from .models import AppSetting, Medicine, MedicineCategory, Membership, Package, UserMark
from .schemas import CategoryOut, MedicineDetail, MedicineOut, PackageOut, StockOut
from .seed import DEFAULT_INDICATION_HINTS

INDICATION_HINTS = "indication_hints"
ACCESS = "access"


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


def find_package_by_serial(db: Session, family_id: int, gtin: str, serial: str) -> Package | None:
    return db.scalar(
        select(Package).join(Medicine)
        .where(Medicine.family_id == family_id, Medicine.gtin == gtin, Package.serial == serial)
    )

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .config import get_settings
from .models import Medicine, Membership, Package, UserMark
from .schemas import CategoryOut, MedicineDetail, MedicineOut, PackageOut, StockOut


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
        .options(selectinload(Medicine.packages), selectinload(Medicine.category), selectinload(Medicine.marks))
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
        id=med.id, name=med.name, category_id=med.category_id, form=med.form, dosage=med.dosage,
        active_ingredient=med.active_ingredient, manufacturer=med.manufacturer,
        indications=med.indications, contraindications=med.contraindications, notes=med.notes,
        unit=med.unit, min_quantity=med.min_quantity, gtin=med.gtin,
        category=CategoryOut.model_validate(med.category) if med.category else None,
        stock=stock_of(med),
        is_favorite=bool(mine and mine.is_favorite),
        helps_me=bool(mine and mine.helps_me),
        personal_note=mine.personal_note if mine else "",
        helps_members=[names[m.user_id] for m in med.marks if m.helps_me and m.user_id != user_id and m.user_id in names],
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

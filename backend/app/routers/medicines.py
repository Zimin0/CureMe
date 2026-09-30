from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session, selectinload

from .. import reminders
from ..codes import parse_code
from ..db import get_db
from ..deps import current_user, get_family
from ..limits import ensure_can_add_medicine
from ..lookup import remember_product
from ..models import Category, Family, Medicine, MedicineCategory, Package, User, UserMark
from ..schemas import (
    ConsumeIn, MarkIn, MedicineDetail, MedicineIn, MedicineOut, MedicineUpdate, PackageIn, PackageOut,
    PackageUpdate,
)
from ..search import best_match
from .files import _drop_photo
from ..services import consume, load_medicines, medicine_out, member_names, record_intake

router = APIRouter(prefix="/api/families/{family_id}/medicines", tags=["medicines"])


def _load_one(db: Session, fam: Family, medicine_id: int) -> Medicine:
    meds = load_medicines(db, fam.id, [medicine_id])
    if not meds:
        raise HTTPException(404, "Лекарство не найдено")
    return meds[0]


def _detail(db: Session, fam: Family, medicine_id: int, user: User) -> MedicineDetail:
    db.expire_all()
    return medicine_out(_load_one(db, fam, medicine_id), user.id, member_names(db, fam.id), detail=True)


def _set_categories(db: Session, med: Medicine, category_ids: list[int]) -> None:
    """Ставит лекарству категории в заданном порядке (первая — основная)."""
    ids = list(dict.fromkeys(category_ids))  # повторы убираем, порядок сохраняем
    if any(db.get(Category, cid) is None for cid in ids):
        raise HTTPException(400, "Категория не найдена")
    keep = {link.category_id: link for link in med.category_links}
    med.category_links = [keep.get(cid) or MedicineCategory(category_id=cid) for cid in ids]
    for pos, link in enumerate(med.category_links):
        link.position = pos


def _normalize_gtin(value: str | None) -> str | None:
    if not value:
        return None
    parsed = parse_code(value)
    if not parsed.gtin:
        raise HTTPException(400, "Код товара не похож на штрихкод EAN/GTIN")
    return parsed.gtin


def _remember(db: Session, med: Medicine) -> None:
    if med.gtin:
        remember_product(
            db, med.gtin, name=med.name, form=med.form, dosage=med.dosage,
            active_ingredient=med.active_ingredient, manufacturer=med.manufacturer,
            unit=med.unit, blister_size=med.blister_size,
        )


@router.get("", response_model=list[MedicineOut])
def list_medicines(
    q: str | None = Query(default=None, max_length=200),
    category_id: int | None = None,
    filter: str | None = Query(default=None, pattern="^(favorites|helps_me|attention|expired|low)$"),
    fam: Family = Depends(get_family),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    names = member_names(db, fam.id)
    items = [medicine_out(m, user.id, names) for m in load_medicines(db, fam.id)]
    if category_id is not None:
        items = [m for m in items if category_id in m.category_ids]
    if filter == "favorites":
        items = [m for m in items if m.is_favorite]
    elif filter == "helps_me":
        items = [m for m in items if m.helps_me]
    elif filter == "expired":
        items = [m for m in items if m.stock.status == "expired"]
    elif filter == "low":
        items = [m for m in items if m.stock.status in ("low", "out")]
    elif filter == "attention":
        items = [m for m in items if m.stock.status != "ok"]
    if q:
        phrases = [(q, 1.0)]
        def hay(m: MedicineOut) -> str:
            return " ".join(filter_none([m.name, m.active_ingredient, m.manufacturer, m.indications, m.form,
                                         *(c.name for c in m.categories), m.gtin]))
        needle = q.strip().lower()
        items = [m for m in items if needle in hay(m).lower() or best_match(phrases, hay(m))[0] > 0]
    return items


def filter_none(xs):
    return [x for x in xs if x]


@router.post("", response_model=MedicineDetail, status_code=201)
def create_medicine(
    body: MedicineIn, fam: Family = Depends(get_family), user: User = Depends(current_user), db: Session = Depends(get_db)
):
    ensure_can_add_medicine(db, fam)
    data = body.model_dump(exclude={"packages", "category_ids"})
    data["gtin"] = _normalize_gtin(body.gtin)
    med = Medicine(family_id=fam.id, created_by_id=user.id, **data)
    _set_categories(db, med, body.category_ids)
    for p in body.packages:
        med.packages.append(Package(added_by_id=user.id, **p.model_dump()))
    db.add(med)
    _remember(db, med)
    db.commit()
    return _detail(db, fam, med.id, user)


@router.get("/{medicine_id}", response_model=MedicineDetail)
def get_medicine(medicine_id: int, fam: Family = Depends(get_family), user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _detail(db, fam, medicine_id, user)


@router.patch("/{medicine_id}", response_model=MedicineDetail)
def update_medicine(
    medicine_id: int, body: MedicineUpdate,
    fam: Family = Depends(get_family), user: User = Depends(current_user), db: Session = Depends(get_db),
):
    med = _load_one(db, fam, medicine_id)
    data = body.model_dump(exclude_unset=True)
    if "category_ids" in data:
        _set_categories(db, med, data.pop("category_ids") or [])
    if "gtin" in data:
        data["gtin"] = _normalize_gtin(data["gtin"])
    for k, v in data.items():
        setattr(med, k, v if v is not None or k in ("min_quantity", "blister_size", "gtin") else getattr(med, k))
    _remember(db, med)
    db.commit()
    return _detail(db, fam, medicine_id, user)


@router.delete("/{medicine_id}", status_code=204)
def delete_medicine(medicine_id: int, fam: Family = Depends(get_family), db: Session = Depends(get_db)):
    med = _load_one(db, fam, medicine_id)
    photo = med.photo
    db.delete(med)
    db.commit()
    _drop_photo(photo)
    return Response(status_code=204)


@router.put("/{medicine_id}/mark", response_model=MedicineDetail)
def mark(
    medicine_id: int, body: MarkIn,
    fam: Family = Depends(get_family), user: User = Depends(current_user), db: Session = Depends(get_db),
):
    _load_one(db, fam, medicine_id)
    m = db.get(UserMark, (user.id, medicine_id)) or UserMark(
        user_id=user.id, medicine_id=medicine_id, is_favorite=False, helps_me=False, personal_note=""
    )
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(m, k, v)
    db.add(m)
    db.commit()
    return _detail(db, fam, medicine_id, user)


@router.post("/{medicine_id}/consume", response_model=MedicineDetail)
def consume_medicine(
    medicine_id: int, body: ConsumeIn,
    fam: Family = Depends(get_family), user: User = Depends(current_user), db: Session = Depends(get_db),
):
    med = _load_one(db, fam, medicine_id)
    short = consume(med, body.amount)
    if short >= body.amount:
        raise HTTPException(400, "В аптечке не осталось годных упаковок")
    record_intake(db, med, user.id, body.amount - short, body.comment)
    db.commit()
    reminders.nudge(fam.id)  # остаток мог опуститься до порога «Напомнить, когда останется»
    return _detail(db, fam, medicine_id, user)


# --- упаковки ---
@router.post("/{medicine_id}/packages", response_model=MedicineDetail, status_code=201)
def add_package(
    medicine_id: int, body: PackageIn,
    fam: Family = Depends(get_family), user: User = Depends(current_user), db: Session = Depends(get_db),
):
    med = _load_one(db, fam, medicine_id)
    if body.serial and any(p.serial == body.serial for p in med.packages):
        raise HTTPException(409, "Эта упаковка уже добавлена (совпадает серийный номер)")
    med.packages.append(Package(added_by_id=user.id, **body.model_dump()))
    db.commit()
    return _detail(db, fam, medicine_id, user)


def _package(med: Medicine, package_id: int) -> Package:
    p = next((p for p in med.packages if p.id == package_id), None)
    if not p:
        raise HTTPException(404, "Упаковка не найдена")
    return p


@router.patch("/{medicine_id}/packages/{package_id}", response_model=MedicineDetail)
def update_package(
    medicine_id: int, package_id: int, body: PackageUpdate,
    fam: Family = Depends(get_family), user: User = Depends(current_user), db: Session = Depends(get_db),
):
    p = _package(_load_one(db, fam, medicine_id), package_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    db.commit()
    reminders.nudge(fam.id)
    return _detail(db, fam, medicine_id, user)


@router.delete("/{medicine_id}/packages/{package_id}", response_model=MedicineDetail)
def delete_package(
    medicine_id: int, package_id: int,
    fam: Family = Depends(get_family), user: User = Depends(current_user), db: Session = Depends(get_db),
):
    med = _load_one(db, fam, medicine_id)
    med.packages.remove(_package(med, package_id))
    db.commit()
    return _detail(db, fam, medicine_id, user)

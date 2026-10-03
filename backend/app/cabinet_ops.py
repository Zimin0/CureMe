"""Перенос лекарств между аптечками одной семьи и разделение аптечки (R17, R18).

Всё делается в одной транзакции под блокировкой семьи. Одинаковые по штрихкоду лекарства сливаются: упаковки
приёмника и источника лежат вместе (остатки складываются), история приёма, расписание и личные отметки уходят на
оставшуюся карточку. Приёмы и расписание остальных лекарств идут за карточкой в новую аптечку.
"""

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from . import households as hh
from .models import Family, Intake, Medicine, Package, Schedule, User, UserMark
from .plans import check_limit, usage
from .routers.files import _drop_photo
from .schemas import MoveOut
from .services import load_medicines


def _merge_marks(db: Session, src: Medicine, dst: Medicine) -> None:
    """Личные отметки (избранное, «помогает мне», заметка) с исчезающей карточки переходят на оставшуюся."""
    have = {m.user_id: m for m in dst.marks}
    for mark in list(src.marks):
        mine = have.get(mark.user_id)
        if mine is None:
            db.add(UserMark(user_id=mark.user_id, medicine_id=dst.id, is_favorite=mark.is_favorite,
                            helps_me=mark.helps_me, personal_note=mark.personal_note))
        else:
            mine.is_favorite = mine.is_favorite or mark.is_favorite
            mine.helps_me = mine.helps_me or mark.helps_me
            mine.personal_note = mine.personal_note or mark.personal_note


def _merge_into(db: Session, src: Medicine, dst: Medicine, dst_family_id: int) -> None:
    db.execute(update(Package).where(Package.medicine_id == src.id).values(medicine_id=dst.id))
    db.execute(update(Intake).where(Intake.medicine_id == src.id).values(medicine_id=dst.id, family_id=dst_family_id))
    db.execute(update(Schedule).where(Schedule.medicine_id == src.id).values(medicine_id=dst.id, family_id=dst_family_id))
    _merge_marks(db, src, dst)
    if dst.photo is None and src.photo is not None:
        dst.photo, src.photo = src.photo, None
    db.flush()
    _drop_photo(src.photo)
    db.expire(src)
    db.delete(src)


def _relocate(db: Session, med: Medicine, dst_family_id: int) -> None:
    med.family_id = dst_family_id
    db.execute(update(Intake).where(Intake.medicine_id == med.id).values(family_id=dst_family_id))
    db.execute(update(Schedule).where(Schedule.medicine_id == med.id).values(family_id=dst_family_id))


def move_medicines(db: Session, user: User, src: Family, dst: Family, medicine_ids: list[int], journal: str = "medicine_move") -> MoveOut:
    """Переносит выбранные лекарства из src в dst (обе из одной семьи, dst не заморожена); дубли по штрихкоду сливает."""
    house = src.household
    hh.lock(db, house)
    if dst.id == src.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Выберите другую аптечку")
    if dst.household_id != src.household_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Аптечка не найдена в вашей семье")
    if dst.status == "frozen":
        raise HTTPException(status.HTTP_409_CONFLICT, "Нельзя переносить лекарства в замороженную аптечку: выберите активную.")
    ids = list(dict.fromkeys(medicine_ids))
    meds = load_medicines(db, src.id, ids)
    if len(meds) != len(ids):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Лекарство не найдено в этой аптечке")
    existing = {m.gtin: m for m in db.scalars(select(Medicine).where(Medicine.family_id == dst.id)) if m.gtin}
    new_cards = sum(1 for m in meds if not (m.gtin and m.gtin in existing))
    if new_cards:
        check_limit(db, dst, "medicines", used=usage(db, dst)["medicines"], adding=new_cards)  # бесплатный лимит 60 не переполняем (R17-T5)
    merged = 0
    for med in meds:
        target = existing.get(med.gtin) if med.gtin else None
        if target is not None:
            _merge_into(db, med, target, dst.id)
            merged += 1
        else:
            _relocate(db, med, dst.id)
    hh.record(db, house, journal, user=user, detail=f"из аптечки №{src.id} в №{dst.id}: {len(meds)}, слито {merged}")
    db.flush()
    return MoveOut(moved=len(meds), merged=merged, to_family_id=dst.id)


def split_cabinet(db: Session, user: User, src: Family, name: str, medicine_ids: list[int]) -> tuple[Family, MoveOut]:
    """Выбранные лекарства уходят в новую аптечку семьи; свободного места нет — 402 с функцией «cabinets» (R18)."""
    fam = hh.create_cabinet(db, user, name)
    db.flush()
    return fam, move_medicines(db, user, src, fam, medicine_ids, journal="cabinet_split")

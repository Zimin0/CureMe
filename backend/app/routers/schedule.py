from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..deps import current_user, get_family
from ..models import Family, Medicine, Schedule, ScheduleSlot, User
from ..reminders import MSK
from ..schedule import occurrences
from ..schemas import (
    MAX_SCHEDULES, MAX_TIMES, OccurrenceOut, ScheduleCreate, ScheduleOut, ScheduleUpdate, SlotMove, SlotsIn,
    SlotsRemove,
)

router = APIRouter(prefix="/api/families/{family_id}/schedule", tags=["schedule"])
MAX_SLOTS = 7 * MAX_TIMES  # приёмов в неделю у одного назначения
MAX_RANGE_DAYS = 31


def _today() -> date:
    return datetime.now(MSK).date()


def _mine(db: Session, fam: Family, user: User, schedule_id: int) -> Schedule:
    """Расписание личное: чужое назначение даже члену семьи не видно (404, а не 403)."""
    s = db.scalar(
        select(Schedule).where(Schedule.id == schedule_id, Schedule.family_id == fam.id, Schedule.user_id == user.id)
        .options(selectinload(Schedule.slots))
    )
    if not s:
        raise HTTPException(404, "Назначение не найдено")
    return s


def _out(s: Schedule) -> ScheduleOut:
    return ScheduleOut.model_validate(s, from_attributes=True)


def _add_slots(db: Session, s: Schedule, days: list[int], times: list[int]) -> int:
    have = {(x.weekday, x.minute) for x in s.slots}
    added = 0
    for d in days:
        for t in times:
            if (d, t) not in have:
                s.slots.append(ScheduleSlot(weekday=d, minute=t))
                added += 1
    if len(s.slots) > MAX_SLOTS:
        raise HTTPException(400, "Слишком много приёмов в одном назначении")
    return added


@router.get("", response_model=list[ScheduleOut])
def list_schedules(fam: Family = Depends(get_family), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Мои назначения в этой аптечке."""
    rows = db.scalars(
        select(Schedule).where(Schedule.family_id == fam.id, Schedule.user_id == user.id)
        .options(selectinload(Schedule.slots)).order_by(Schedule.medicine_name, Schedule.id)
    )
    return [_out(s) for s in rows]


@router.get("/occurrences", response_model=list[OccurrenceOut])
def list_occurrences(
    since: date | None = None, until: date | None = None,
    fam: Family = Depends(get_family), user: User = Depends(current_user), db: Session = Depends(get_db),
):
    """Приёмы на период (по умолчанию — сегодня) с отметкой «принят» из истории приёма."""
    first = since or _today()
    last = until or first
    if last < first or (last - first).days >= MAX_RANGE_DAYS:
        raise HTTPException(400, f"Период — от 1 до {MAX_RANGE_DAYS} дней")
    return [
        OccurrenceOut(
            schedule_id=o.schedule.id, slot_id=o.slot_id, medicine_id=o.schedule.medicine_id,
            medicine_name=o.schedule.medicine_name, unit=o.schedule.unit, amount=o.schedule.amount,
            date=o.day, minute=o.minute, taken=o.taken_at is not None, taken_at=o.taken_at,
        )
        for o in occurrences(db, user.id, first, last, fam.id)
    ]


@router.post("", response_model=ScheduleOut, status_code=201)
def create_schedule(
    body: ScheduleCreate, fam: Family = Depends(get_family), user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    med = db.scalar(select(Medicine).where(Medicine.id == body.medicine_id, Medicine.family_id == fam.id))
    if not med:
        raise HTTPException(404, "Лекарство не найдено")
    count = db.scalar(select(func.count()).select_from(Schedule).where(Schedule.user_id == user.id)) or 0
    if count >= MAX_SCHEDULES:
        raise HTTPException(400, "Слишком много назначений: уберите ненужные")
    s = Schedule(
        family_id=fam.id, user_id=user.id, medicine_id=med.id, medicine_name=med.name, unit=med.unit,
        amount=body.amount, start_date=body.start_date or _today(), end_date=body.end_date,
        every_weeks=body.every_weeks,
    )
    db.add(s)
    _add_slots(db, s, body.days, body.times)
    db.commit()
    return _out(s)


@router.patch("/{schedule_id}", response_model=ScheduleOut)
def update_schedule(
    schedule_id: int, body: ScheduleUpdate, fam: Family = Depends(get_family), user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    s = _mine(db, fam, user, schedule_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is None and k != "end_date":
            continue  # очистить можно только дату окончания («бессрочно»)
        setattr(s, k, v)
    if s.end_date and s.end_date < s.start_date:
        raise HTTPException(400, "Дата окончания раньше даты начала")
    db.commit()
    return _out(s)


@router.delete("/{schedule_id}", status_code=204)
def delete_schedule(
    schedule_id: int, fam: Family = Depends(get_family), user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    db.delete(_mine(db, fam, user, schedule_id))
    db.commit()
    return Response(status_code=204)


@router.post("/{schedule_id}/slots", response_model=ScheduleOut)
def add_slots(
    schedule_id: int, body: SlotsIn, fam: Family = Depends(get_family), user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    s = _mine(db, fam, user, schedule_id)
    _add_slots(db, s, body.days, body.times)
    db.commit()
    return _out(s)


@router.post("/{schedule_id}/remove", response_model=ScheduleOut | None)
def remove_slots(
    schedule_id: int, body: SlotsRemove, fam: Family = Depends(get_family),
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    """Убирает приёмы серией (см. SlotsRemove). Если приёмов не осталось, назначение удаляется: ответ 204."""
    s = _mine(db, fam, user, schedule_id)
    days, times = set(body.days), set(body.times)
    gone = [x for x in s.slots if (not days or x.weekday in days) and (not times or x.minute in times)]
    if not days and not times:
        gone = list(s.slots)  # пустой запрос — убрать всё назначение
    if not gone:
        raise HTTPException(404, "Таких приёмов в назначении нет")
    for x in gone:
        s.slots.remove(x)
    if not s.slots:
        db.delete(s)
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    db.commit()
    return _out(s)


@router.patch("/{schedule_id}/slots/{slot_id}", response_model=ScheduleOut)
def move_slot(
    schedule_id: int, slot_id: int, body: SlotMove, fam: Family = Depends(get_family),
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    """Перетащить приём на другой день или время."""
    s = _mine(db, fam, user, schedule_id)
    slot = next((x for x in s.slots if x.id == slot_id), None)
    if not slot:
        raise HTTPException(404, "Приём не найден")
    weekday = slot.weekday if body.weekday is None else body.weekday
    minute = slot.minute if body.minute is None else body.minute
    if any(x.id != slot.id and (x.weekday, x.minute) == (weekday, minute) for x in s.slots):
        raise HTTPException(409, "На это время приём уже назначен")
    slot.weekday, slot.minute = weekday, minute
    db.commit()
    return _out(s)

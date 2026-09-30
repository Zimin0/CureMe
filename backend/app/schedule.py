"""Расписание приёма: какие приёмы выпадают на дату и принят ли каждый (по истории приёма).

Время везде московское, как и у напоминаний. Приём «принят», если в истории приёма этого человека
есть запись о том же лекарстве в окне вокруг назначенного времени: начинается за час до приёма
(принял чуть раньше — тоже засчитываем) и кончается через три часа после. Если у одного
лекарства приёмы идут чаще, окно сужается до середины промежутка, чтобы одна таблетка
не закрыла сразу два приёма.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .models import Intake, Schedule
from .reminders import MSK
from .services import _aware

EARLY = 60   # минут до назначенного времени, за которые приём ещё засчитывается
LATE = 180   # минут после


def is_active_on(s: Schedule, day: date) -> bool:
    """Идёт ли назначение в этот день: внутри периода и в «свою» неделю при повторе «через N недель»."""
    if day < s.start_date or (s.end_date and day > s.end_date):
        return False
    monday = lambda d: d - timedelta(days=d.weekday())  # noqa: E731
    return ((monday(day) - monday(s.start_date)).days // 7) % s.every_weeks == 0


@dataclass
class Occurrence:
    schedule: Schedule
    slot_id: int
    day: date
    minute: int
    window_start: datetime
    window_end: datetime
    taken_at: datetime | None = None

    @property
    def due(self) -> datetime:
        return datetime.combine(self.day, datetime.min.time(), tzinfo=MSK) + timedelta(minutes=self.minute)


def occurrences(db: Session, user_id: int, first: date, last: date, family_id: int | None = None) -> list[Occurrence]:
    """Все приёмы человека на даты first..last включительно с отметкой «принят», по возрастанию времени."""
    q = select(Schedule).where(Schedule.user_id == user_id).options(selectinload(Schedule.slots))
    if family_id is not None:
        q = q.where(Schedule.family_id == family_id)
    schedules = db.scalars(q).all()
    found: list[Occurrence] = []
    day = first
    while day <= last:
        for s in schedules:
            if is_active_on(s, day):
                found += [Occurrence(s, sl.id, day, sl.minute, datetime.min, datetime.min)
                          for sl in s.slots if sl.weekday == day.weekday()]
        day += timedelta(days=1)
    _fit_windows(found)
    _mark_taken(db, user_id, found)
    return sorted(found, key=lambda o: (o.due, o.schedule.id, o.slot_id))


def _fit_windows(items: list[Occurrence]) -> None:
    """Окно приёма: [due − EARLY, due + LATE], но не дальше середины промежутка до соседнего приёма того же лекарства."""
    by_med: dict[tuple, list[Occurrence]] = {}
    for o in items:
        by_med.setdefault((o.schedule.medicine_id or -o.schedule.id, o.day), []).append(o)
    for group in by_med.values():
        group.sort(key=lambda o: o.minute)
        for i, o in enumerate(group):
            before = EARLY if i == 0 else min(EARLY, (o.minute - group[i - 1].minute) / 2)
            after = LATE if i == len(group) - 1 else min(LATE, (group[i + 1].minute - o.minute) / 2)
            o.window_start = o.due - timedelta(minutes=before)
            o.window_end = o.due + timedelta(minutes=after)


def _mark_taken(db: Session, user_id: int, items: list[Occurrence]) -> None:
    if not items:
        return
    ids = {o.schedule.medicine_id for o in items if o.schedule.medicine_id}
    if not ids:
        return
    # SQLite хранит время без пояса, поэтому границы запроса приводим к UTC, как и записи в истории.
    lo = min(o.window_start for o in items).astimezone(timezone.utc)
    hi = max(o.window_end for o in items).astimezone(timezone.utc)
    intakes = db.scalars(
        select(Intake).where(Intake.user_id == user_id, Intake.medicine_id.in_(ids),
                             Intake.taken_at >= lo, Intake.taken_at <= hi).order_by(Intake.taken_at)
    ).all()
    used: set[int] = set()  # одна запись в истории закрывает только один приём
    for o in sorted(items, key=lambda o: o.due):
        for i in intakes:
            if i.id in used or i.medicine_id != o.schedule.medicine_id:
                continue
            t = _aware(i.taken_at)
            if o.window_start <= t <= o.window_end:
                o.taken_at = t
                used.add(i.id)
                break

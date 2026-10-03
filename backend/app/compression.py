"""Окончание Плюса и сжатие семьи (R13, R14, docs/household-model).

Как это устроено:
- T0 — момент, когда Плюс семьи кончился: срок `plus_until` или возврат денег (R15). Платные функции закрываются
  сразу, а всё, что превышает бесплатные лимиты (люди, аптечки), остаётся доступным ещё 5 дней.
- В эти дни владелец сам выбирает, кто остаётся и какие аптечки остаются активными (`choose`). Выбор действует сразу.
- Если он не выбрал, через 5 дней (`compress`) остаются владелец и самые давние по вступлению люди, остальные
  переходят в личные семьи (то же, что выход, R09, без кулдауна), лишние аптечки замораживаются: только просмотр
  и выгрузка, без срока. Ничего не удаляется. Оплата Плюса снимает заморозку (`restore`).
- Письмо владельцу за 3 дня до конца, в день конца, через 3 и 4 дня; после сжатия письма владельцу и отключённым.
  Состояние ведут два поля семьи: `plus_ended_at` (T0) и `compress_stage` (последняя ступень писем).
- Всё это включается одной настройкой в админке (`enabled`), по умолчанию выключено: пока в Соглашении нет
  опубликованного текста о сжатии, после окончания Плюса происходит только то, что было раньше.

Фоновый проход `run` вызывается раз в минуту из reminders.py и идемпотентен: повторный запуск ничего не меняет.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from . import households as hh
from .mailer import send_mail
from .models import AppSetting, Family, Household, User
from .plans import FREE_CABINETS_MAX, OLD_FREE_MEMBERS, PLUS, free_members_limit, house_has_plus, limit_for, plus_active

log = logging.getLogger("cureme.compression")

KEY = "compression"
COMPRESS_DAYS = 5  # compress_days: сколько дней после конца Плюса владелец выбирает состав сам
NOTICE_BEFORE = timedelta(days=3)  # письмо «Плюс заканчивается» за столько дней до конца

# Ступени писем в households.compress_stage.
ENDING, ENDED, REMIND_3, REMIND_4, DONE = 1, 2, 3, 4, 5


# --- настройка в админке ---
def enabled(db: Session) -> bool:
    row = db.get(AppSetting, KEY)
    return bool((row.value if row else None) and row.value.get("enabled"))


def set_enabled(db: Session, value: bool) -> bool:
    row = db.get(AppSetting, KEY)
    if row:
        row.value = {"enabled": value}
    else:
        db.add(AppSetting(key=KEY, value={"enabled": value}))
    db.commit()
    return value


# --- что превышает бесплатные лимиты ---
def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _msk(moment: datetime) -> str:
    return moment.astimezone(timezone(timedelta(hours=3))).strftime("%d.%m.%Y")


def people_limit(now: datetime, house: Household | None = None) -> int:
    """Сколько людей остаётся в семье после сжатия: бесплатный предел на этот день (R02).

    Семье, где было четверо до 13.10.2026, остаются четверо (Соглашение п. 6.12): иначе заплативший и потом
    отключившийся Плюс оказался бы в худшем положении, чем тот, кто не платил.
    """
    limit = free_members_limit(now)
    return max(limit, OLD_FREE_MEMBERS) if house is not None and house.kept_four else limit


def cabinet_cap(people: int) -> int:
    """Сколько активных аптечек у бесплатной семьи из стольких людей (R03)."""
    return min(max(people, 1), FREE_CABINETS_MAX)


@dataclass
class Plan:
    """Что случится с семьёй при сжатии: кто остаётся, кто уходит, какие аптечки заморозятся."""

    keep: list[User]
    leaving: list[User]
    frozen: list[Family]
    stay: frozenset[int] = frozenset()  # аптечки, которые владелец выбрал оставить: уходящий их не забирает


def plan_compression(house: Household, now: datetime, keep_user_ids: set[int] | None = None,
                     keep_cabinet_ids: set[int] | None = None) -> Plan:
    """Расчёт без изменений. Без выбора владельца остаются он и самые давние по вступлению (при равенстве по номеру).

    Уходящие забирают по одной аптечке, созданной ими (как при выходе, R09); из того, что осталось семье, активными
    остаются самые давние по дате создания, но не больше, чем людей, остальные замораживаются.
    """
    members = hh.people(house)  # владелец первым, дальше самые давние
    owner = hh.owner_of(house)
    if keep_user_ids is None:
        keep = members[:people_limit(now, house)]
    else:
        keep = [u for u in members if u.id in keep_user_ids or u is owner]
    leaving = [u for u in members if u not in keep]
    keep_cabinet_ids = keep_cabinet_ids or None  # пустой выбор значит «как обычно»: самые давние
    stay = keep_cabinet_ids or set()
    active = hh.active_cabinets(house)
    taken = {next((c.id for c in active if c.created_by_id == u.id and c.id not in stay), None) for u in leaving} - {None}
    left = [c for c in active if c.id not in taken]
    cap = cabinet_cap(len(keep))
    chosen = [c for c in left if c.id in keep_cabinet_ids][:cap] if keep_cabinet_ids is not None else left[:cap]
    return Plan(keep=keep, leaving=leaving, frozen=[c for c in left if c not in chosen], stay=frozenset(stay))


def over_limit(db: Session, house: Household, now: datetime) -> bool:
    """В семье людей или активных аптечек больше, чем бесплатно (при Плюсе или выключенной платной версии: нет)."""
    if house_has_plus(db, house):
        return False
    plan = plan_compression(house, now)
    return bool(plan.leaving or plan.frozen)


def _owner_autorenews(house: Household) -> bool:
    owner = hh.owner_of(house)
    return bool(owner and owner.auto_renew and owner.pay_method_id)


def episode_start(house: Household, now: datetime) -> datetime | None:
    """T0 текущего окончания Плюса: записанный или, если запись ещё не сделана, конец оплаченного срока."""
    if house.plus_ended_at is not None:
        return _aware(house.plus_ended_at)
    if house.plan == PLUS and house.plus_until is not None and _aware(house.plus_until) <= now:
        return _aware(house.plus_until)
    return None


def mark_ended(house: Household, now: datetime) -> None:
    """Плюс снят вручную (администратор): окно выбора начинается сейчас."""
    if house.plus_ended_at is None:
        house.plus_ended_at = now
        house.compress_stage = 0


# --- письма (без ссылок: почта Яндекса отклоняет письма со ссылкой на сайт) ---
MSK_NOTE = "\n\nВсе даты в письме указаны по московскому времени."
SIGN = "\n\n— Капсулка, домашняя аптечка"


def _facts(house: Household, now: datetime) -> dict:
    plan = plan_compression(house, now)
    return {"n": len(house.members), "c": len(hh.active_cabinets(house)), "limit": people_limit(now, house),
            "k": len(plan.leaving), "m": len(plan.frozen)}


def _ending_letter(name: str, until: datetime, f: dict) -> tuple[str, str]:
    d, d5 = _msk(until), _msk(until + timedelta(days=COMPRESS_DAYS))
    return (f"Капсулка: Плюс вашей семьи заканчивается {d}",
            f"Здравствуйте, {name}!\n\nПодписка Капсулка Плюс вашей семьи закончится {d}. Автопродление выключено, деньги не спишутся. "
            f"С этой даты платные функции закроются сразу.\n\nВ семье сейчас {f['n']} человек и {f['c']} активных аптечек, а бесплатно можно "
            f"{f['limit']} человек и столько аптечек, сколько людей. Поэтому у вас будет ещё {COMPRESS_DAYS} дней, до {d5}, чтобы выбрать, "
            "кто и какие аптечки остаются: до этого срока всё остаётся доступным. Ничего не удаляется: лишние аптечки остаются "
            "замороженными (их можно смотреть и выгружать), а людей мы переводим в их личные семьи с их данными.\n\n"
            "Чтобы ничего не менялось, продлите Плюс на странице «Плюс» в приложении." + MSK_NOTE + SIGN)


def _ended_letter(name: str, t0: datetime, f: dict) -> tuple[str, str]:
    d5 = _msk(t0 + timedelta(days=COMPRESS_DAYS))
    return ("Капсулка: Плюс вашей семьи закончился",
            f"Здравствуйте, {name}!\n\nПодписка Капсулка Плюс вашей семьи закончилась. В семье сейчас {f['n']} человек и {f['c']} аптечек. "
            f"Бесплатно можно {f['limit']} человек и столько аптечек, сколько людей.\n\nДо {d5} всё остаётся доступным: выберите на странице "
            f"«Семья» в приложении, кто остаётся и какие аптечки остаются активными. Если выбора не будет, {d5} останетесь вы и самые давние по "
            f"вступлению участники (всего {f['limit']}), остальные {f['k']} человек перейдут в личные семьи со своей аптечкой, а {f['m']} аптечек "
            "будут заморожены: их можно смотреть и выгружать, но нельзя менять. Ничего не удаляется.\n\n"
            "После оплаты Плюса заморозка снимается сразу, а отключённых людей можно снова пригласить." + MSK_NOTE + SIGN)


def _remind_letter(name: str, t0: datetime, f: dict, days_left: int) -> tuple[str, str]:
    d5 = _msk(t0 + timedelta(days=COMPRESS_DAYS))
    left = "2 дня" if days_left == 2 else "1 день"
    return (f"Капсулка: осталось {left} на выбор состава семьи",
            f"Здравствуйте, {name}!\n\n{d5} без вашего выбора {f['k']} человек семьи перейдут в личные семьи, а {f['m']} аптечек будут "
            "заморожены (смотреть и выгружать можно, менять нельзя). Ничего не удаляется.\n\n"
            "Выбрать, кто и какие аптечки остаются, можно на странице «Семья» в приложении, а продление Плюса отменяет всё это." + MSK_NOTE + SIGN)


def _done_owner_letter(name: str, plan: Plan) -> tuple[str, str]:
    return ("Капсулка: состав семьи сжат",
            f"Здравствуйте, {name}!\n\nСжатие семьи выполнено: остались {len(plan.keep)} человек, {len(plan.leaving)} перешли в личные семьи, "
            f"{len(plan.frozen)} аптечек заморожены. Ничего не удалено.\n\n"
            "Продление Плюса снимает заморозку, отключённых людей можно пригласить заново без ожидания." + SIGN)


def _moved_letter(name: str, cabinet: str) -> tuple[str, str]:
    return ("Капсулка: вы перенесены в личную семью",
            f"Здравствуйте, {name}!\n\nПлюс семьи закончился, и вы перешли в личную семью: вы её владелец. Ваши приёмы, расписание и "
            f"избранное остались с вами, с вами и ваша аптечка «{cabinet}». Лекарства других аптечек прежней семьи вам больше не видны. "
            "Ничего не удалено.\n\nВладелец прежней семьи может пригласить вас снова. Если вы не согласны, ответьте на это письмо." + SIGN)


def _mail(user: User | None, letter: tuple[str, str]) -> None:
    if user is not None:
        send_mail(user.email, letter[0], letter[1])


# --- действия ---
def freeze(cabinets: list[Family]) -> None:
    for c in cabinets:
        c.status = "frozen"


def restore(db: Session, house: Household) -> bool:
    """Плюс снова идёт: замороженные аптечки оживают (не больше предела Плюса), окно выбора закрывается."""
    changed = False
    cap = limit_for(db, house, "own_families")
    for c in hh.cabinets_of(house):
        if c.status == "frozen" and (cap is None or len(hh.active_cabinets(house)) < cap):
            c.status = "active"
            changed = True
    if house.plus_ended_at is not None or house.compress_stage >= ENDED:
        house.plus_ended_at, house.compress_stage, changed = None, 0, True
    return changed


def apply(db: Session, house: Household, plan: Plan, now: datetime) -> None:
    """Выполняет расчёт: уходящие переходят в личные семьи, лишние аптечки замораживаются."""
    moved: list[tuple[User, Family]] = []
    for user in plan.leaving:
        taken = hh.leave(db, user, actor=None, kicked=True, detail="сжатие после окончания Плюса", stay_ids=plan.stay, kind="compress")
        moved.append((user, taken))
    freeze([c for c in hh.cabinets_of(house) if c in plan.frozen])
    for user, cabinet in moved:
        _mail(user, _moved_letter(user.name, cabinet.name))
    db.flush()


def compress(db: Session, house: Household, now: datetime) -> Plan:
    """Сжатие без выбора владельца (R14). Идемпотентно: у семьи в пределах лимитов ничего не меняется."""
    hh.lock(db, house)
    plan = plan_compression(house, now)
    if plan.leaving or plan.frozen:
        apply(db, house, plan, now)
        _mail(hh.owner_of(house), _done_owner_letter(hh.owner_of(house).name, plan))
    house.compress_stage = DONE
    return plan


def choose(db: Session, owner: User, keep_user_ids: list[int], keep_cabinet_ids: list[int],
           now: datetime | None = None) -> Plan:
    """Владелец сам выбирает, кто остаётся и какие аптечки остаются активными (R13-T4). Применяется сразу."""
    now = now or datetime.now(timezone.utc)
    house = owner.household
    hh.lock(db, house)
    if not enabled(db):
        raise HTTPException(status.HTTP_409_CONFLICT, "Выбор состава семьи сейчас недоступен")
    if hh.owner_of(house) is not owner:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Это может сделать только владелец семьи")
    if house_has_plus(db, house) or episode_start(house, now) is None or house.compress_stage >= DONE:
        raise HTTPException(status.HTTP_409_CONFLICT, "Сейчас выбирать состав не нужно: Плюс идёт или состав уже выбран")
    if not over_limit(db, house, now):
        raise HTTPException(status.HTTP_409_CONFLICT, "Семья укладывается в бесплатные лимиты, выбирать нечего")
    members = {u.id for u in house.members}
    cabinets = {c.id for c in hh.active_cabinets(house)}
    if not set(keep_user_ids) <= members or not set(keep_cabinet_ids) <= cabinets:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Человек или аптечка не из вашей семьи")
    keep_people = set(keep_user_ids) | {owner.id}
    limit = people_limit(now, house)
    if len(keep_people) > limit:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"В бесплатной семье не больше {limit} человек, вместе с вами")
    if len(set(keep_cabinet_ids)) > cabinet_cap(len(keep_people)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Активных аптечек столько, сколько людей: не больше {cabinet_cap(len(keep_people))}")
    plan = plan_compression(house, now, set(keep_user_ids), set(keep_cabinet_ids))
    apply(db, house, plan, now)
    house.compress_stage = DONE
    return plan


def unfreeze(db: Session, fam: Family) -> None:
    """Владелец размораживает одну аптечку, если есть свободное место (удалили активную или людей стало больше)."""
    house = fam.household
    hh.lock(db, house)
    if fam.status != "frozen":
        raise HTTPException(status.HTTP_409_CONFLICT, "Аптечка не заморожена")
    cap = limit_for(db, house, "own_families")
    if cap is not None and len(hh.active_cabinets(house)) >= cap:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Свободного места для аптечки нет: активных аптечек уже столько, сколько людей в семье. Удалите другую аптечку или подключите Плюс.",
        )
    fam.status = "active"


# --- фоновый проход ---
def _step(db: Session, house: Household, now: datetime) -> None:
    hh.lock(db, house)
    if house_has_plus(db, house):
        restore(db, house)
        until = _aware(house.plus_until) if house.plus_until is not None else None
        if until is not None and house.plan == PLUS:
            if now < until - NOTICE_BEFORE:
                house.compress_stage = 0 if house.compress_stage == ENDING else house.compress_stage
            elif house.compress_stage < ENDING and not _owner_autorenews(house):
                if over_limit_after(db, house, until):
                    owner = hh.owner_of(house)
                    _mail(owner, _ending_letter(owner.name, until, _facts(house, until)))
                house.compress_stage = ENDING
        return
    t0 = episode_start(house, now)
    if t0 is None:
        return
    if house.plus_ended_at is None:
        house.plus_ended_at = t0
    elapsed = now - t0
    stage = (DONE if elapsed >= timedelta(days=COMPRESS_DAYS) else REMIND_4 if elapsed >= timedelta(days=4)
             else REMIND_3 if elapsed >= timedelta(days=3) else ENDED)
    if stage <= house.compress_stage:
        return
    if not over_limit(db, house, now):
        house.compress_stage = stage  # укладывается в лимиты: письма не нужны
        return
    owner = hh.owner_of(house)
    if stage == DONE:
        compress(db, house, now)
        return
    facts = _facts(house, now)
    _mail(owner, _ended_letter(owner.name, t0, facts) if stage == ENDED
          else _remind_letter(owner.name, t0, facts, 2 if stage == REMIND_3 else 1))
    house.compress_stage = stage


def over_limit_after(db: Session, house: Household, moment: datetime) -> bool:
    """Будет ли семья превышать бесплатные лимиты, когда Плюс кончится (сейчас он ещё идёт)."""
    plan = plan_compression(house, moment)
    return bool(plan.leaving or plan.frozen)


def thaw_all(db: Session) -> int:
    """Настройку выключили (возврат к прежнему поведению): замороженные аптечки снова активны, окна выбора закрыты."""
    frozen = db.scalars(select(Family).where(Family.status == "frozen")).all()
    for fam in frozen:
        fam.status = "active"
    for house in db.scalars(select(Household).where(or_(Household.plus_ended_at.is_not(None), Household.compress_stage > 0))):
        house.plus_ended_at, house.compress_stage = None, 0
    if frozen:
        db.commit()
    return len(frozen)


def run(db: Session, now: datetime | None = None) -> int:
    """Раз в минуту: письма, сжатие, снятие заморозки. Возвращает, у скольких семей что-то изменилось."""
    if not enabled(db):
        return thaw_all(db)
    now = now or datetime.now(timezone.utc)
    frozen_houses = select(Family.household_id).where(Family.status == "frozen", Family.household_id.is_not(None))
    houses = db.scalars(select(Household).where(or_(
        Household.plan == PLUS, Household.plus_ended_at.is_not(None), Household.compress_stage > 0,
        Household.id.in_(frozen_houses),
    ))).all()
    changed = 0
    for house in houses:
        before = (house.plus_ended_at, house.compress_stage, tuple(c.status for c in house.cabinets))
        try:
            _step(db, house, now)
            db.commit()
        except Exception:  # noqa: BLE001
            log.exception("Окончание Плюса семьи %s: сбой, продолжаем с остальными", house.id)
            db.rollback()
            continue
        db.refresh(house)
        changed += before != (house.plus_ended_at, house.compress_stage, tuple(c.status for c in house.cabinets))
    return changed


def banner(db: Session, user: User, now: datetime | None = None) -> dict | None:
    """Что показать наверху приложения всем людям семьи: Плюс заканчивается или закончился и идёт окно выбора."""
    now = now or datetime.now(timezone.utc)
    house = user.household
    if house is None or not enabled(db):
        return None
    owner = hh.owner_of(house)
    base = {"is_owner": owner is not None and owner.id == user.id, "people_limit": people_limit(now, house)}
    if house_has_plus(db, house):
        until = _aware(house.plus_until) if house.plus_until is not None else None
        if (until is not None and house.plan == PLUS and now >= until - NOTICE_BEFORE and not _owner_autorenews(house)
                and over_limit_after(db, house, until)):
            return {"state": "ending", "date": until, **base}
        return None
    t0 = episode_start(house, now)
    if t0 is None or house.compress_stage >= DONE or not over_limit(db, house, now):
        return None
    return {"state": "ended", "date": t0 + timedelta(days=COMPRESS_DAYS), **base}

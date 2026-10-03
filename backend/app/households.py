"""Семья и аптечки: единственное место, где меняется состав семьи и список аптечек (docs/household-model).

Семья (Household) — люди с общим тарифом и одним владельцем. Аптечка — строка таблицы families.
Тариф и лимиты считает plans.py. Доступ к данным аптечки по-прежнему проверяется по таблице memberships,
поэтому любое изменение состава или аптечек заканчивается sync_access: у каждого человека семьи есть доступ
ко всем аптечкам семьи и ни к чему больше. Роутеры состав напрямую не меняют.

Каждая операция сначала берёт блокировку строки семьи (lock), а потом проверяет лимиты по свежим данным:
два одновременных вступления при одном свободном месте не пройдут оба (R20).
"""
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from .models import Family, Household, HouseholdEvent, Intake, Medicine, Membership, Schedule, User, utcnow
from .plans import (
    FREE_LIMITS, LIMIT_FEATURE, PLUS_MEMBERS_MAX, PLUS_OWN_FAMILIES_MAX, limit_for, plus_active, plus_required,
)
from .routers.files import _drop_photo
from .security import new_invite_code
from .seed import ensure_default_categories


# --- чтение ---
def lock(db: Session, house: Household) -> None:
    """Блокирует строку семьи до конца транзакции и сбрасывает прочитанные списки: дальше считаем по свежим данным."""
    db.flush()
    db.execute(select(Household.id).where(Household.id == house.id).with_for_update())
    db.expire(house, ["members", "cabinets"])


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)  # SQLite отдаёт время без пояса


def people(house: Household) -> list[User]:
    """Люди семьи: владелец первым, дальше по времени вступления."""
    return sorted(house.members, key=lambda u: (u.household_role != "owner", _aware(u.household_joined_at), u.id))


def owner_of(house: Household | None) -> User | None:
    return next((u for u in house.members if u.household_role == "owner"), None) if house else None


def cabinets_of(house: Household) -> list[Family]:
    return sorted(house.cabinets, key=lambda f: (_aware(f.created_at), f.id))


def _is_empty(db: Session, fam: Family) -> bool:
    return db.scalar(select(Medicine.id).where(Medicine.family_id == fam.id).limit(1)) is None


def record(db: Session, house: Household | None, kind: str, user: User | None = None,
           actor: User | None = None, detail: str = "") -> None:
    db.add(HouseholdEvent(household_id=house.id if house else None, kind=kind,
                          user_id=user.id if user else None, actor_id=actor.id if actor else None, detail=detail))


# --- доступ ---
def sync_access(db: Session, house: Household) -> None:
    """Выравнивает memberships: каждый человек семьи имеет доступ к каждой аптечке семьи, роль в аптечке равна роли в семье."""
    db.flush()
    db.expire(house, ["members", "cabinets"])
    members = {u.id: u for u in house.members}
    for fam in house.cabinets:
        db.expire(fam, ["memberships"])
        have = {m.user_id: m for m in fam.memberships}
        for uid, m in have.items():
            if uid not in members:
                db.delete(m)
            elif m.role != members[uid].household_role:
                m.role = members[uid].household_role
        for uid, user in members.items():
            if uid not in have:
                db.add(Membership(family_id=fam.id, user_id=uid, role=user.household_role, joined_at=user.household_joined_at))
    db.flush()
    for user in house.members:
        db.expire(user, ["memberships"])


# --- лимиты ---
def ensure_room_for_person(db: Session, house: Household, joining: bool = False) -> None:
    """В семье есть место ещё для одного человека (R02). Бесплатный предел — 402 со шторкой Плюса, потолок Плюса — 409."""
    limit = limit_for(db, house, "members")
    if limit is None or len(house.members) < limit:
        return
    if limit >= PLUS_MEMBERS_MAX:
        raise HTTPException(status.HTTP_409_CONFLICT, f"В семье уже {limit} человек: это предел Капсулки Плюс.")
    then = ("Попросите владельца семьи подключить Капсулку Плюс: с ней в семье до "
            f"{PLUS_MEMBERS_MAX} человек." if joining else f"В Капсулке Плюс в семье до {PLUS_MEMBERS_MAX} человек.")
    raise plus_required(LIMIT_FEATURE["members"], f"В семье уже {limit} человека: это предел бесплатной версии. {then}")


def members_full(db: Session, house: Household) -> bool:
    """В семье уже предел людей: приглашение принять нельзя (для экрана приглашения)."""
    limit = limit_for(db, house, "members")
    return limit is not None and len(house.members) >= limit


def ensure_room_for_cabinets(db: Session, house: Household, adding: int = 1, people: int | None = None) -> None:
    """Аптечек не станет больше, чем разрешено семье (R03). Уже созданные сверх лимита не трогаем."""
    limit = limit_for(db, house, "own_families", people)
    if limit is None or len(house.cabinets) + adding <= limit:
        return
    if limit >= PLUS_OWN_FAMILIES_MAX:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"В семье может быть не больше {PLUS_OWN_FAMILIES_MAX} аптечек. Нужно больше — напишите нам.",
        )
    raise plus_required(
        LIMIT_FEATURE["own_families"],
        f"В бесплатной версии аптечек столько же, сколько людей в семье (не больше {FREE_LIMITS['members']}). "
        "В Капсулке Плюс — до 8: дача, машина, бабушка.",
    )


# --- создание ---
def add_cabinet(db: Session, house: Household, name: str, creator: User | None) -> Family:
    fam = Family(name=name, invite_code=new_invite_code(), household=house, created_by_id=creator.id if creator else None)
    db.add(fam)
    ensure_default_categories(db)
    sync_access(db, house)
    return fam


def create_personal(db: Session, user: User) -> Family:
    """Личная семья из одного человека с одной пустой аптечкой (R01). Пользователь уже сохранён (есть id)."""
    house = Household()
    db.add(house)
    user.household, user.household_role, user.household_joined_at = house, "owner", utcnow()
    return add_cabinet(db, house, f"Семья {user.name}", user)


def attach(db: Session, user: User, house: Household) -> None:
    """Новый аккаунт, пришедший по приглашению, становится участником семьи (R01: личная семья ему не создаётся)."""
    user.household, user.household_role, user.household_joined_at = house, "member", utcnow()
    record(db, house, "join", user=user, detail="регистрация по приглашению")
    sync_access(db, house)


def create_cabinet(db: Session, user: User, name: str) -> Family:
    house = user.household
    lock(db, house)
    ensure_room_for_cabinets(db, house)
    fam = add_cabinet(db, house, name, user)
    record(db, house, "cabinet_add", user=user, detail=name)
    return fam


# --- состав ---
def _move_history(db: Session, user: User, from_ids: list[int], to: Family) -> None:
    """Приёмы человека идут с ним (R19): записи переезжают в его аптечку, название лекарства в них уже скопировано."""
    if from_ids:
        db.execute(update(Intake).where(Intake.user_id == user.id, Intake.family_id.in_(from_ids))
                   .values(family_id=to.id, medicine_id=None))


def stop_autorenew(user: User) -> None:
    """Карта привязана к человеку, а платит он за семью: сменил владельца, ушёл — автопродление выключаем (R21)."""
    user.auto_renew, user.pay_method_id, user.renew_period = False, None, None
    user.renew_notified_for = user.renew_notified_at = None


def join(db: Session, user: User, target: Household, actor: User | None = None, force: bool = False) -> None:
    """Человек, который живёт один, вступает в чужую семью (R08).

    Бесплатный приносит свою аптечку с лекарствами, пустая растворяется. Пробный Плюс личной семьи пропадает вместе
    с ней (R07). Если у человека оплачен Плюс, вступить нельзя: оплаченные дни пропали бы (до выбора по R08 «а/б/в»).
    force — администратор сервиса вносит человека сверх лимитов (по просьбе семьи); остальные проверки остаются.
    """
    mine = user.household
    if mine is target:
        return
    # Блокировки берём по возрастанию id: встречные вступления двух людей друг к другу не ждут друг друга вечно.
    for house in sorted([target] + ([mine] if mine is not None else []), key=lambda h: h.id):
        lock(db, house)
    if mine is not None:
        if len(mine.members) > 1:
            raise HTTPException(status.HTTP_409_CONFLICT, "Сначала выйдите из своей семьи: вступить в другую можно, только если живёшь один.")
        if plus_active(mine) and not mine.plus_is_trial:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "У вашей семьи оплачен Плюс, и при вступлении он пропадёт. Напишите нам, мы поможем перенести оплаченные дни.",
            )
    if not force:
        ensure_room_for_person(db, target, joining=True)
    own = cabinets_of(mine) if mine is not None else []
    bring = [c for c in own if c.status == "active" and not _is_empty(db, c)]
    if len(bring) > 1 or any(c not in bring and not _is_empty(db, c) for c in own):
        raise HTTPException(status.HTTP_409_CONFLICT, "У вас несколько аптечек с лекарствами. Оставьте одну: перенесите лекарства или удалите лишние.")
    if not bring and own and not target.cabinets:
        bring = [own[0]]  # у семьи нет ни одной аптечки: пустая аптечка человека не пропадёт, в ней его история приёма
    if not force:
        ensure_room_for_cabinets(db, target, adding=len(bring), people=len(target.members) + 1)

    dissolved = [c for c in own if c not in bring]
    target_first = cabinets_of(target)[0] if target.cabinets else None
    for fam in bring:
        fam.household = target
    user.household, user.household_role, user.household_joined_at = target, "member", utcnow()
    db.flush()
    # История приёма растворённой аптечки идёт с человеком в первую аптечку семьи (или в ту, что он принёс).
    home = bring[0] if bring else target_first
    if home is not None:
        _move_history(db, user, [c.id for c in dissolved], home)
    for fam in dissolved:
        db.expire(fam)
        db.delete(fam)
    db.flush()
    if mine is not None:
        db.expire(mine, ["members", "cabinets"])
        db.delete(mine)
    record(db, target, "join", user=user, actor=actor)
    sync_access(db, target)


def leave(db: Session, user: User, actor: User | None = None, kicked: bool = False) -> Family:
    """Человек уходит из семьи (R09) или его исключает владелец (R10): новая личная семья и одна аптечка, созданная им.

    Остальные его аптечки остаются семье. Приёмы человека переезжают с ним, расписание по оставшимся аптечкам
    удаляется (лекарства там ему больше недоступны). Возвращает аптечку, с которой он ушёл.
    """
    house = user.household
    lock(db, house)
    if len(house.members) < 2:
        raise HTTPException(status.HTTP_409_CONFLICT, "Вы живёте один: покидать нечего. Лишнюю аптечку можно удалить, а аккаунт удалить в профиле.")
    if user.household_role == "owner":
        raise HTTPException(status.HTTP_409_CONFLICT, "Владелец семьи сначала передаёт владение другому человеку.")
    own = [c for c in cabinets_of(house) if c.created_by_id == user.id and c.status == "active"]
    keep = own[0] if own else None
    left_ids = [c.id for c in house.cabinets if c is not keep]

    new_house = Household()
    db.add(new_house)
    user.household, user.household_role, user.household_joined_at = new_house, "owner", utcnow()
    db.flush()
    if keep is not None:
        # Приёмы тех, кто остаётся, не уезжают вместе с аптечкой: переносим их в аптечку прежней семьи.
        stay_home = next((c for c in cabinets_of(house) if c is not keep), None)
        if stay_home is None:
            stay_home = add_cabinet(db, house, f"Семья {owner_of(house).name}", owner_of(house))
        for other in house.members:
            if other.id != user.id:
                _move_history(db, other, [keep.id], stay_home)
        keep.household = new_house
    else:
        keep = add_cabinet(db, new_house, f"Семья {user.name}", user)
    _move_history(db, user, left_ids, keep)
    db.execute(delete(Schedule).where(Schedule.user_id == user.id, Schedule.family_id.in_(left_ids)))
    record(db, house, "kick" if kicked else "leave", user=user, actor=actor)
    sync_access(db, house)
    sync_access(db, new_house)
    return keep


def make_owner(db: Session, house: Household, new_owner: User, actor: User | None = None) -> None:
    """Владелец один (R02): новый владелец назначается, прежний становится участником, его автопродление выключается."""
    lock(db, house)
    old = owner_of(house)
    if old is new_owner:
        return
    if old is not None:
        old.household_role = "member"
        stop_autorenew(old)
    new_owner.household_role = "owner"
    record(db, house, "owner", user=new_owner, actor=actor, detail=f"прежний владелец: {old.name if old else 'нет'}")
    sync_access(db, house)


# --- аптечки и аккаунты ---
def drop_cabinet_files(db: Session, fam: Family) -> None:
    for name in db.scalars(select(Medicine.photo).where(Medicine.family_id == fam.id, Medicine.photo.is_not(None))):
        _drop_photo(name)


def delete_cabinet(db: Session, fam: Family, actor: User | None = None, force: bool = False) -> None:
    """Удаляет аптечку с лекарствами, упаковками, приёмами и расписаниями. Последнюю удалить нельзя (R24), администратор может."""
    house = fam.household
    if house is not None:
        lock(db, house)
        if not force and len(house.cabinets) <= 1:
            raise HTTPException(status.HTTP_409_CONFLICT, "Это последняя аптечка семьи: удалить её нельзя. Создайте другую или выгрузите данные.")
    drop_cabinet_files(db, fam)
    record(db, house, "cabinet_delete", actor=actor, detail=fam.name)
    db.delete(fam)
    db.flush()
    if house is not None:
        db.expire(house, ["cabinets"])


def delete_account(db: Session, user: User, admin: bool = False) -> None:
    """Готовит удаление аккаунта (R22); саму строку человека удаляет вызывающий.

    Аптечки, которые создал человек, остаются семье. Если он последний, семья удаляется целиком.
    Владелец при других людях сначала передаёт владение; администратор передаёт его самому давнему участнику.
    """
    house = user.household
    if house is None:
        return
    lock(db, house)
    others = [u for u in people(house) if u.id != user.id]
    if not others:
        for fam in list(house.cabinets):
            drop_cabinet_files(db, fam)
        db.delete(house)
        db.flush()
        return
    if user.household_role == "owner":
        if not admin:
            raise HTTPException(status.HTTP_409_CONFLICT, "Вы владелец семьи: сначала передайте владение другому человеку.")
        make_owner(db, house, others[0])
    stop_autorenew(user)
    record(db, house, "leave", user=user, detail="удаление аккаунта")
    user.household = None
    sync_access(db, house)


def invariant_problems(db: Session) -> list[str]:
    """Что нарушено в данных (R01–R03): человек вне семьи, у семьи не один владелец, лимиты, доступ не равен людям × аптечкам.

    Пустой список — всё в порядке. Проверка идёт после каждого сценария тестов (R20-T3).
    """
    problems: list[str] = []
    for u in db.scalars(select(User).where(User.household_id.is_(None))):
        problems.append(f"R01: у человека {u.id} нет семьи")
    access = {(m.family_id, m.user_id): m.role for m in db.scalars(select(Membership))}
    expected: dict[tuple[int, int], str] = {}
    for house in db.scalars(select(Household)):
        members = list(house.members)
        owners = [u for u in members if u.household_role == "owner"]
        if len(owners) != 1:
            problems.append(f"R02: у семьи {house.id} владельцев {len(owners)}")
        limit = limit_for(db, house, "members")
        if limit is not None and len(members) > limit:
            problems.append(f"R02: в семье {house.id} людей {len(members)} при лимите {limit}")
        limit = limit_for(db, house, "own_families")
        if limit is not None and len(house.cabinets) > limit:
            problems.append(f"R03: в семье {house.id} аптечек {len(house.cabinets)} при лимите {limit}")
        for fam in house.cabinets:
            for u in members:
                expected[(fam.id, u.id)] = u.household_role
    for fam in db.scalars(select(Family).where(Family.household_id.is_(None))):
        problems.append(f"аптечка {fam.id} не принадлежит семье")
    if access != expected:
        problems.append(f"доступ не совпадает с людьми × аптечками: лишнее {sorted(set(access) - set(expected))}, "
                        f"нет {sorted(set(expected) - set(access))}")
    return problems

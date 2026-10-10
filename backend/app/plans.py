"""Тарифы «Бесплатный» и «Плюс»: что даёт Плюс, лимиты бесплатной версии и проверки.

Все лимиты и список платных функций живут здесь, чтобы их было легко менять.
Подписка на семью (docs/household-model): тариф хранится у семьи (Household.plan, Household.plus_until)
и действует на всех её людей и все её аптечки. Платит владелец семьи (правило R06 вводится отдельным шагом).

Пока администратор не включил платную версию (настройка billing в app_settings),
у всех семей работает всё, как в Плюсе. Так выкладка не урезает сайт у тех, кто уже им пользуется.

Как пользоваться в роутерах:
    require_plus(db, family, "export_pdf")                     # 402, если у семьи нет Плюса
    check_limit(db, family, "medicines", used=count, adding=1)  # 402, если превысили лимит
    since = history_since(db, family)                           # None или граница «последних 30 дней»
или зависимостью: dependencies=[Depends(plus_feature("reminders"))].
"""
import calendar
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import get_db
from .deps import family_membership
from .models import AppSetting, Family, Household, Medicine, Membership, User
from .schemas import BillingSettings, PlanFeatureOut, PlanOut
from .services import telegram_active

FREE = "free"
PLUS = "plus"
PLANS = (FREE, PLUS)

# Лимиты бесплатной версии. В Плюсе ограничений нет.
FREE_LIMITS: dict[str, int] = {
    "members": 3,        # человек в бесплатной семье (R02)
    "medicines": 60,     # лекарств в одной аптечке (R26)
    "own_families": 1,   # аптечек у одного человека; в бесплатной семье их столько, сколько людей (R03)
    "history_days": 30,  # сколько дней истории приёма видно
}
# Новая редакция Соглашения (п. 6.2: в бесплатной семье до 3 человек вместо 4) вступает в силу через десять
# дней после публикации (п. 11.2 Соглашения). До этого момента действует прежний предел. Семьи, где людей уже
# больше нового предела, не затрагиваются: никого не исключаем, только не принимаем новых.
NEW_TERMS_FROM = datetime(2026, 10, 12, 21, 0, tzinfo=timezone.utc)  # 13 октября 2026 г., 00:00 по Москве
OLD_FREE_MEMBERS = 4
MAX_AHEAD_MONTHS = 13  # Плюс семьи нельзя оплатить или перенести дальше чем на столько месяцев вперёд (R06, R08)
FREE_CABINETS_MAX = 3  # потолок аптечек бесплатной семьи, как бы ни менялся предел людей (R03)
# Потолки Плюса (R02, R03): защита от того, что одна подписка держит десятки людей и аптечек.
PLUS_MEMBERS_MAX = 5
PLUS_OWN_FAMILIES_MAX = 8  # аптечек в семье с Плюсом
LIMIT_LABELS = {
    "members": "участников в семье",
    "medicines": "лекарств в аптечке",
    "own_families": "своих аптечек",
    "history_days": "дней истории приёма",
}

# Функции Плюса: ключ → (название, одна фраза для шторки «доступно в Плюсе»).
# Ключи общие с фронтендом (frontend/src/plan.tsx).
FEATURES: dict[str, tuple[str, str]] = {
    "reminders": (
        "Напоминания в Telegram и на почту",
        "Напомним, когда лекарство заканчивается или скоро истечёт срок годности.",
    ),
    "full_history": (
        "Вся история приёма",
        "История приёма за всё время и поиск по ней. Бесплатно видны последние 30 дней.",
    ),
    "export_pdf": (
        "Экспорт в PDF и Excel для врача",
        "Список лекарств и история приёма в файле, который удобно показать врачу. Бесплатно — текстовый список.",
    ),
    "cabinets": (
        "Несколько своих аптечек",
        "Отдельные аптечки для дачи, машины или бабушки. Бесплатно — одна своя.",
    ),
    "schedule": (
        "Расписание приёма",
        "Добавляйте назначения в расписание. Бесплатно уже созданное можно смотреть, отмечать и удалять.",
    ),
    "search_all": (
        "Поиск по всем аптечкам",
        "Ищите лекарства и подбирайте «что есть дома от…» сразу во всех аптечках семьи. Бесплатно — в открытой аптечке.",
    ),
    "shelf_plan": (
        "Где лежит лекарство",
        "Схема полок и контейнеров аптечки и отметка на ней, где лежит каждое лекарство. Бесплатно уже сделанное можно смотреть и убирать.",
    ),
    "illness": (
        "История болезней",
        "Новые записи с датами, комментарием и фото справок. Бесплатно уже созданные записи можно смотреть, править и удалять.",
    ),
    "no_limits": (
        "Без лимитов",
        "Сколько угодно участников и лекарств. Бесплатно — до 4 участников и 60 лекарств.",
    ),
}
# Какая функция Плюса снимает лимит: её показывает шторка, когда лимит исчерпан.
LIMIT_FEATURE = {"members": "no_limits", "medicines": "no_limits", "own_families": "cabinets",
                 "history_days": "full_history"}

BILLING = "billing"  # ключ в app_settings
DEFAULT_TRIAL_DAYS = 5  # пробный Плюс при первом подтверждении почты; меняется в админке «Капсулка Плюс»
PLUS_HEADER = "X-Plus-Feature"  # в ответе 402: какую функцию Плюса открыть в шторке


def billing_settings(db: Session) -> BillingSettings:
    """Включена ли платная версия и сколько стоит Плюс. По умолчанию выключена: всем доступно всё."""
    row = db.get(AppSetting, BILLING)
    value = (row.value if row else None) or {}
    return BillingSettings(
        enabled=bool(value.get("enabled")), price_month=value.get("price_month"), price_year=value.get("price_year"),
        trial_days=value.get("trial_days", DEFAULT_TRIAL_DAYS), plus_theme=bool(value.get("plus_theme", True)),
    )


def set_billing_settings(db: Session, body: BillingSettings) -> BillingSettings:
    row = db.get(AppSetting, BILLING)
    if row:
        row.value = body.model_dump()
    else:
        db.add(AppSetting(key=BILLING, value=body.model_dump()))
    db.commit()
    return body


def grant_trial(db: Session, user: User) -> bool:
    """Дарит пробный Плюс новому аккаунту один раз. Вызывать, когда почта подтверждена (без коммита).

    Срок берётся из настройки trial_days (0 — выключено). Оплаченный или уже выданный Плюс не трогаем.
    Пробный получает только личная семья из одного человека (R07): тому, кто пришёл по приглашению в чужую
    семью, пробный не даётся, иначе свежие аккаунты по очереди давали бы чужой семье вечный Плюс.
    После окончания семья просто возвращается на бесплатный тариф, деньги не списываются.
    """
    days = billing_settings(db).trial_days
    house = user.household
    if days <= 0 or user.trial_granted_at is not None or house is None or plus_active(house):
        return False
    if user.household_role != "owner" or len(house.members) != 1:
        return False
    now = datetime.now(timezone.utc)
    house.plan = PLUS
    house.plus_until = now + timedelta(days=days)
    house.plus_is_trial = True
    user.trial_granted_at = now
    return True


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)  # SQLite отдаёт время без пояса


def shift_months(moment: datetime, months: int) -> datetime:
    """Сдвиг на целые календарные месяцы (назад при отрицательном числе); 31-е в коротком месяце становится его последним днём."""
    index = moment.year * 12 + moment.month - 1 + months
    year, month = divmod(index, 12)
    month += 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


def plus_active(who: "User | Household | None", now: datetime | None = None) -> bool:
    """Оплачен ли Плюс у семьи сейчас (без учёта того, включена ли платная версия). Принимает человека или семью."""
    house = who.household if isinstance(who, User) else who
    if house is None or house.plan != PLUS:
        return False
    return house.plus_until is None or _aware(house.plus_until) > (now or datetime.now(timezone.utc))


def household_owner(house: Household | None) -> User | None:
    """Владелец семьи (R02): ровно один."""
    if house is None:
        return None
    return next((u for u in house.members if u.household_role == "owner"), None)


def family_owner_user(family: Family) -> User | None:
    """Владелец семьи, которой принадлежит аптечка."""
    return household_owner(family.household)


def family_plus_active(family: Family, now: datetime | None = None) -> bool:
    """Оплачен ли Плюс у аптечки: у её семьи."""
    return plus_active(family.household, now)


def house_has_plus(db: Session, house: Household | None) -> bool:
    """Доступно ли семье всё, что есть в Плюсе: Плюс оплачен или платная версия выключена."""
    return plus_active(house) or not billing_settings(db).enabled


def has_plus(db: Session, family: Family) -> bool:
    return house_has_plus(db, family.household)


def free_members_limit(now: datetime | None = None) -> int:
    """Сколько людей в бесплатной семье: 4 до вступления в силу новой редакции Соглашения, потом 3 (R02)."""
    return FREE_LIMITS["members"] if (now or datetime.now(timezone.utc)) >= NEW_TERMS_FROM else OLD_FREE_MEMBERS


def free_limits() -> dict[str, int]:
    return {**FREE_LIMITS, "members": free_members_limit()}


def limit_for(db: Session, house: Household | None, name: str, people: int | None = None) -> int | None:
    """Действующий лимит семьи или None, если лимита нет.

    Бесплатно: людей 3, лекарств 60 на аптечку, история 30 дней, аптечек столько, сколько людей, но не больше 3 (R03).
    С Плюсом: людей 5, аптечек 8, остального без ограничений. people позволяет спросить «а если людей станет столько».
    """
    if house_has_plus(db, house):
        return {"members": PLUS_MEMBERS_MAX, "own_families": PLUS_OWN_FAMILIES_MAX}.get(name)
    if name == "own_families":
        count = people if people is not None else (len(house.members) if house else 1)
        return min(max(count, 1), FREE_CABINETS_MAX)
    return free_members_limit() if name == "members" else FREE_LIMITS[name]


def limit_of(db: Session, family: Family, name: str) -> int | None:
    return limit_for(db, family.household, name)


REMINDERS_WITH_TELEGRAM = "Напоминания в Telegram и на почту"
REMINDERS_EMAIL_ONLY = "Напоминания на почту"  # пока Telegram выключен в админке, о нём не говорим


def feature_title(feature: str, telegram_on: bool = False) -> str:
    title = FEATURES[feature][0]
    return title if telegram_on or title != REMINDERS_WITH_TELEGRAM else REMINDERS_EMAIL_ONLY


def plus_required(feature: str, message: str | None = None) -> HTTPException:
    title = feature_title(feature)
    return HTTPException(
        status.HTTP_402_PAYMENT_REQUIRED,
        message or f"«{title}» доступно в Капсулке Плюс",
        headers={PLUS_HEADER: feature},
    )


def require_plus(db: Session, family: Family, feature: str) -> None:
    if feature not in FEATURES:
        raise ValueError(f"Неизвестная функция Плюса: {feature}")
    if not has_plus(db, family):
        raise plus_required(feature)


def require_house_plus(db: Session, house: Household | None, feature: str) -> None:
    """То же, что require_plus, но по семье человека: для личных функций, не привязанных к аптечке (история болезней)."""
    if feature not in FEATURES:
        raise ValueError(f"Неизвестная функция Плюса: {feature}")
    if not house_has_plus(db, house):
        raise plus_required(feature)


def check_limit(db: Session, family: Family, name: str, used: int, adding: int = 1) -> None:
    """402, если после добавления adding штук станет больше лимита. Уже набранное сверх лимита не трогаем."""
    limit = limit_of(db, family, name)
    if limit is not None and used + adding > limit:
        raise plus_required(
            LIMIT_FEATURE[name],
            f"В бесплатной версии не больше {limit} {LIMIT_LABELS[name]}. В Капсулке Плюс ограничений нет.",
        )


def history_since(db: Session, family: Family, now: datetime | None = None) -> datetime | None:
    """С какого момента показывать историю приёма; None — всю."""
    days = limit_of(db, family, "history_days")
    return None if days is None else (now or datetime.now(timezone.utc)) - timedelta(days=days)


def own_families_left(db: Session, user_id: int) -> int | None:
    """Сколько аптечек ещё можно завести в семье человека (R03). None — платная версия выключена, считать нечего."""
    user = db.get(User, user_id)
    house = user.household if user else None
    if house is None:
        return 0
    left = max((limit_for(db, house, "own_families") or 0) - len([c for c in house.cabinets if c.status == "active"]), 0)
    return left if left == 0 or billing_settings(db).enabled else None


def usage(db: Session, family: Family) -> dict[str, int]:
    medicines = db.scalar(select(func.count()).select_from(Medicine).where(Medicine.family_id == family.id)) or 0
    members = len(family.household.members) if family.household else len(family.memberships)
    return {"members": members, "medicines": medicines}


def plan_out(db: Session, family: Family) -> PlanOut:
    billing = billing_settings(db)
    enabled = billing.enabled
    house = family.household
    owner = household_owner(house)
    active = plus_active(house)
    plus = active or not enabled
    tg_on = telegram_active(db)
    return PlanOut(
        plan=house.plan if house else "free",
        plus_until=house.plus_until if house else None,
        plus_active=active,
        owner_name=owner.name if owner else None,
        billing_enabled=enabled,
        plus_theme=billing.plus_theme,
        price_month=billing.price_month,
        price_year=billing.price_year,
        has_plus=plus,
        limits={k: limit_of(db, family, k) for k in FREE_LIMITS},
        free_limits=free_limits(),
        usage=usage(db, family),
        features=[PlanFeatureOut(key=k, title=feature_title(k, tg_on), description=d, available=plus) for k, (_, d) in FEATURES.items()],
    )


def plus_feature(feature: str):
    """Зависимость для эндпоинтов семьи: пропускает только семьи с Плюсом (иначе 402)."""
    if feature not in FEATURES:
        raise ValueError(f"Неизвестная функция Плюса: {feature}")

    def dep(m: Membership = Depends(family_membership), db: Session = Depends(get_db)) -> Family:
        require_plus(db, m.family, feature)
        return m.family

    return dep

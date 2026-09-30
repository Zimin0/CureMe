"""Тарифы «Бесплатный» и «Плюс»: что даёт Плюс, лимиты бесплатной версии и проверки.

Все лимиты и список платных функций живут здесь, чтобы их было легко менять.
Подписка семейная: тариф хранится у семьи (Family.plan, Family.plus_until), а не у человека.

Пока администратор не включил платную версию (настройка billing в app_settings),
у всех семей работает всё, как в Плюсе. Так выкладка не урезает сайт у тех, кто уже им пользуется.

Как пользоваться в роутерах:
    require_plus(db, family, "export_pdf")                     # 402, если у семьи нет Плюса
    check_limit(db, family, "medicines", used=count, adding=1)  # 402, если превысили лимит
    since = history_since(db, family)                           # None или граница «последних 30 дней»
или зависимостью: dependencies=[Depends(plus_feature("reminders"))].
"""
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import get_db
from .deps import family_membership
from .models import AppSetting, Family, Medicine, Membership
from .schemas import BillingSettings, PlanFeatureOut, PlanOut

FREE = "free"
PLUS = "plus"
PLANS = (FREE, PLUS)

# Лимиты бесплатной версии. В Плюсе ограничений нет.
FREE_LIMITS: dict[str, int] = {
    "members": 4,        # участников в семье
    "medicines": 60,     # лекарств в аптечке
    "own_families": 1,   # своих аптечек (где человек владелец); вступать в чужие можно без ограничений
    "history_days": 30,  # сколько дней истории приёма видно
}
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
    "no_limits": (
        "Без лимитов",
        "Сколько угодно участников и лекарств. Бесплатно — до 4 участников и 60 лекарств.",
    ),
}
# Какая функция Плюса снимает лимит: её показывает шторка, когда лимит исчерпан.
LIMIT_FEATURE = {"members": "no_limits", "medicines": "no_limits", "own_families": "cabinets",
                 "history_days": "full_history"}

BILLING = "billing"  # ключ в app_settings
PLUS_HEADER = "X-Plus-Feature"  # в ответе 402: какую функцию Плюса открыть в шторке


def billing_settings(db: Session) -> BillingSettings:
    """Включена ли платная версия и сколько стоит Плюс. По умолчанию выключена: всем доступно всё."""
    row = db.get(AppSetting, BILLING)
    value = (row.value if row else None) or {}
    return BillingSettings(
        enabled=bool(value.get("enabled")), price_month=value.get("price_month"), price_year=value.get("price_year"),
    )


def set_billing_settings(db: Session, body: BillingSettings) -> BillingSettings:
    row = db.get(AppSetting, BILLING)
    if row:
        row.value = body.model_dump()
    else:
        db.add(AppSetting(key=BILLING, value=body.model_dump()))
    db.commit()
    return body


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)  # SQLite отдаёт время без пояса


def plus_active(family: Family, now: datetime | None = None) -> bool:
    """Оплачен ли Плюс у семьи сейчас (без учёта того, включена ли платная версия)."""
    if family.plan != PLUS:
        return False
    return family.plus_until is None or _aware(family.plus_until) > (now or datetime.now(timezone.utc))


def has_plus(db: Session, family: Family) -> bool:
    """Доступно ли семье всё, что есть в Плюсе: Плюс оплачен или платная версия выключена."""
    return plus_active(family) or not billing_settings(db).enabled


def limit_of(db: Session, family: Family, name: str) -> int | None:
    """Лимит бесплатной версии для семьи или None, если лимита нет."""
    return None if has_plus(db, family) else FREE_LIMITS[name]


def plus_required(feature: str, message: str | None = None) -> HTTPException:
    title = FEATURES[feature][0]
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
    """Сколько ещё своих аптечек может создать человек; None — без ограничений.

    Если хотя бы у одной его семьи есть Плюс (или платная версия выключена), ограничения нет.
    """
    owned = list(db.scalars(
        select(Family).join(Membership).where(Membership.user_id == user_id, Membership.role == "owner")
    ))
    if not billing_settings(db).enabled or any(plus_active(f) for f in owned):
        return None
    return max(FREE_LIMITS["own_families"] - len(owned), 0)


def usage(db: Session, family: Family) -> dict[str, int]:
    count = lambda model, col: db.scalar(select(func.count()).select_from(model).where(col == family.id)) or 0  # noqa: E731
    return {"members": count(Membership, Membership.family_id), "medicines": count(Medicine, Medicine.family_id)}


def plan_out(db: Session, family: Family) -> PlanOut:
    billing = billing_settings(db)
    enabled = billing.enabled
    plus = plus_active(family) or not enabled
    return PlanOut(
        plan=family.plan,
        plus_until=family.plus_until,
        plus_active=plus_active(family),
        billing_enabled=enabled,
        price_month=billing.price_month,
        price_year=billing.price_year,
        has_plus=plus,
        limits={k: (None if plus else v) for k, v in FREE_LIMITS.items()},
        free_limits=FREE_LIMITS,
        usage=usage(db, family),
        features=[PlanFeatureOut(key=k, title=t, description=d, available=plus) for k, (t, d) in FEATURES.items()],
    )


def plus_feature(feature: str):
    """Зависимость для эндпоинтов семьи: пропускает только семьи с Плюсом (иначе 402)."""
    if feature not in FEATURES:
        raise ValueError(f"Неизвестная функция Плюса: {feature}")

    def dep(m: Membership = Depends(family_membership), db: Session = Depends(get_db)) -> Family:
        require_plus(db, m.family, feature)
        return m.family

    return dep

"""Лимиты бесплатной версии в действиях: до 4 участников и 60 лекарств в одной аптечке.

Сами лимиты и тариф семьи — в plans.py; здесь только проверки перед добавлением.
Считаем карточки лекарств, а не упаковки: лекарство с нулевым остатком тоже занимает место,
потому что остаётся в списке и в истории приёма. Семьи, которые набрали больше
до появления лимитов, ничего не теряют: запрещено только добавлять новое.
"""

from sqlalchemy.orm import Session

from .models import Family
from .plans import check_limit, limit_of, plus_required, usage


def ensure_can_add_medicine(db: Session, family: Family) -> None:
    check_limit(db, family, "medicines", used=usage(db, family)["medicines"])


def members_full(db: Session, family: Family) -> bool:
    """В семье уже предел участников бесплатной версии (для экрана приглашения)."""
    limit = limit_of(db, family, "members")
    return limit is not None and usage(db, family)["members"] >= limit


def ensure_can_add_member(db: Session, family: Family, joining: bool = False) -> None:
    """joining — человек сам вступает по приглашению; иначе его добавляет администратор сервиса."""
    if not members_full(db, family):
        return
    limit = limit_of(db, family, "members")
    then = ("Попросите владельца семьи подключить Капсулку Плюс: с ней участников сколько угодно." if joining
            else "В Капсулке Плюс участников сколько угодно.")
    raise plus_required("no_limits", f"В семье «{family.name}» уже {limit} участника: это предел бесплатной версии. {then}")

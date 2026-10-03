"""Лимиты бесплатной версии в действиях: 3 человека в семье, аптечек по числу людей и 60 лекарств в одной аптечке.

Сами лимиты и тариф семьи — в plans.py, проверки состава и аптечек — в households.py; здесь только проверка
перед добавлением лекарства. Считаем карточки лекарств, а не упаковки: лекарство с нулевым остатком тоже занимает
место, потому что остаётся в списке и в истории приёма. Семьи, которые набрали больше до появления лимитов,
ничего не теряют: запрещено только добавлять новое.
"""

from sqlalchemy.orm import Session

from .models import Family
from .plans import check_limit, usage


def ensure_can_add_medicine(db: Session, family: Family) -> None:
    check_limit(db, family, "medicines", used=usage(db, family)["medicines"])

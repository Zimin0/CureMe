"""Бизнес-логика остатков: статус лекарства и списание по принципу FEFO.

Здесь не нужна база: вместо моделей SQLAlchemy — простые объекты-«заглушки»
с теми же полями (SimpleNamespace). Так тест быстрый и проверяет только логику.
"""

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.config import get_settings
from app.services import consume, stock_of

TODAY = date(2026, 9, 26)
SOON = get_settings().expiring_soon_days


def pkg(qty, days=None, id=1, opened=None):
    return SimpleNamespace(
        id=id, quantity=qty, opened_at=opened,
        expiry_date=None if days is None else TODAY + timedelta(days=days),
    )


def med(*packages, min_quantity=None):
    return SimpleNamespace(packages=list(packages), min_quantity=min_quantity)


@pytest.mark.parametrize("m, status", [
    (med(pkg(10, 400)), "ok"),
    (med(pkg(10)), "ok"),                                     # без срока годности
    (med(), "out"),
    (med(pkg(0, 400)), "out"),
    (med(pkg(10, SOON)), "expiring"),                         # ровно на границе
    (med(pkg(10, SOON + 1)), "ok"),
    (med(pkg(10, 0)), "expiring"),                            # истекает сегодня — ещё годно
    (med(pkg(10, -1)), "expired"),
    (med(pkg(10, 400), pkg(1, -1)), "expired"),               # просрочка важнее всего
    (med(pkg(10, 400), pkg(0, -1)), "ok"),                    # пустая просроченная упаковка не считается
    (med(pkg(3, 400), min_quantity=5), "low"),
    (med(pkg(5, 400), min_quantity=5), "low"),                # порог включительно
    (med(pkg(6, 400), min_quantity=5), "ok"),
    (med(pkg(3, 5), min_quantity=5), "expiring"),             # срок важнее остатка
])
def test_stock_status(m, status):
    assert stock_of(m, today=TODAY).status == status


def test_stock_numbers():
    s = stock_of(med(pkg(10, 400), pkg(2.5, 20), pkg(4, -3), pkg(0, 100)), today=TODAY)
    assert s.total == 12.5
    assert s.expired_quantity == 4
    assert s.package_count == 3              # пустые упаковки не считаем
    assert s.nearest_expiry == TODAY + timedelta(days=20)
    assert s.days_left == 20


def test_stock_without_dates():
    s = stock_of(med(pkg(3)), today=TODAY)
    assert s.nearest_expiry is None and s.days_left is None


# --- списание ------------------------------------------------------------------
# consume() берёт «сегодня» из date.today(), поэтому сроки считаем от настоящей даты.

def real(qty, days=None, id=1, opened=None):
    p = pkg(qty, None, id, opened)
    p.expiry_date = None if days is None else date.today() + timedelta(days=days)
    return p


def test_consume_takes_earliest_expiry_first():
    late, early, nodate = real(10, 300, id=1), real(4, 10, id=2), real(5, None, id=3)
    short = consume(med(late, nodate, early), 6)
    assert short == 0
    assert (early.quantity, late.quantity, nodate.quantity) == (0, 8, 5)


def test_consume_packages_without_date_go_last():
    dated, nodate = real(2, 300, id=2), real(5, None, id=1)
    consume(med(nodate, dated), 3)
    assert (dated.quantity, nodate.quantity) == (0, 4)


def test_consume_skips_expired():
    expired, good = real(10, -1, id=1), real(3, 30, id=2)
    short = consume(med(expired, good), 5)
    assert expired.quantity == 10 and good.quantity == 0 and short == 2


def test_consume_marks_package_opened():
    first, second = real(10, 10, id=1), real(10, 20, id=2, opened=date(2026, 1, 1))
    consume(med(first, second), 12)
    assert first.opened_at == date.today()
    assert second.opened_at == date(2026, 1, 1)  # дату первого вскрытия не перезаписываем


def test_consume_fractional():
    p = real(1, 30)
    consume(med(p), 0.25)
    consume(med(p), 0.25)
    assert p.quantity == 0.5


def test_consume_from_empty_returns_full_shortage():
    assert consume(med(), 3) == 3

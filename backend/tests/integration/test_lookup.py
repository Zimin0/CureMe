"""Справочник товаров: локальный кеш, поиск в интернете, Open Food Facts.

Настоящий интернет в тестах не нужен и вреден (медленно, нестабильно), поэтому
сетевые функции подменяем через monkeypatch — это и есть «моки».
"""

from types import SimpleNamespace

import httpx
import pytest

from app import lookup
from app.lookup import find_product, lookup_openfoodfacts, remember_product
from app.models import ProductCode
from app.websearch import WebProduct

GTIN = "04601669002013"
# В приложении сессия с autoflush=False, и каждый запрос заканчивается commit().
# Поэтому и здесь между «запросами» делаем db.commit().


@pytest.fixture
def online(monkeypatch):
    monkeypatch.setattr(lookup, "get_settings", lambda: SimpleNamespace(remote_lookup=True))


def test_remember_requires_name(db):
    assert remember_product(db, GTIN, name=None) is None
    assert db.get(ProductCode, GTIN) is None


def test_remember_keeps_only_product_fields(db):
    remember_product(db, GTIN, name="Нурофен", dosage="200 мг", notes="личная заметка", unit=None)
    db.commit()
    row = db.get(ProductCode, GTIN)
    assert (row.name, row.dosage, row.unit, row.source) == ("Нурофен", "200 мг", None, "user")
    assert not hasattr(row, "notes")


def test_user_edit_beats_internet_but_not_vice_versa(db):
    remember_product(db, GTIN, source="internet", name="Нурофен", title="Нурофен таблетки №10")
    db.commit()
    remember_product(db, GTIN, source="user", name="Нурофен Экспресс")
    db.commit()
    assert db.get(ProductCode, GTIN).source == "user"
    remember_product(db, GTIN, source="internet", name="Нурофен таб")
    db.commit()
    row = db.get(ProductCode, GTIN)
    assert row.source == "user" and row.title == "Нурофен таблетки №10"


def test_offline_returns_only_cache(db, monkeypatch):
    monkeypatch.setattr(lookup, "search_barcode", lambda ean: pytest.fail("сеть выключена"))
    assert find_product(db, GTIN) is None
    remember_product(db, GTIN, name="Нурофен")
    db.commit()
    assert find_product(db, GTIN, refresh=True).name == "Нурофен"


def test_web_result_is_saved_with_blister_guess(db, online, monkeypatch):
    seen = []
    monkeypatch.setattr(lookup, "search_barcode", lambda ean: seen.append(ean) or WebProduct(
        name="Нурофен", title="Нурофен таблетки 200 мг №20", form="Таблетки", dosage="200 мг", pack_size=20, unit="таб"))
    row = find_product(db, GTIN)
    db.commit()
    assert seen == ["4601669002013"]  # ищем привычный EAN-13 без ведущего нуля
    assert (row.source, row.pack_size, row.blister_size) == ("internet", 20, 10)
    # второй вызов берёт из кеша
    monkeypatch.setattr(lookup, "search_barcode", lambda ean: pytest.fail("должно быть в кеше"))
    assert find_product(db, GTIN).title == "Нурофен таблетки 200 мг №20"


def test_falls_back_to_openfoodfacts(db, online, monkeypatch):
    monkeypatch.setattr(lookup, "search_barcode", lambda ean: None)
    monkeypatch.setattr(lookup, "lookup_openfoodfacts", lambda gtin: {"name": "Аскорбинка", "manufacturer": "Марбиофарм"})
    row = find_product(db, GTIN)
    assert (row.name, row.manufacturer, row.source) == ("Аскорбинка", "Марбиофарм", "openfoodfacts")


def test_nothing_found_anywhere(db, online, monkeypatch):
    monkeypatch.setattr(lookup, "search_barcode", lambda ean: None)
    monkeypatch.setattr(lookup, "lookup_openfoodfacts", lambda gtin: None)
    assert find_product(db, GTIN) is None


def fake_http(monkeypatch, response=None, error=None):
    def get(url, **kw):
        assert url.endswith("/4601669002013.json")
        if error:
            raise error
        return response
    monkeypatch.setattr(lookup.httpx, "get", get)


@pytest.mark.parametrize("payload, expected", [
    ({"status": 1, "product": {"product_name_ru": "Аскорбинка", "product_name": "Ascorbic", "brands": "Марбиофарм"}},
     {"name": "Аскорбинка", "manufacturer": "Марбиофарм"}),
    ({"status": 1, "product": {"product_name": "Ascorbic"}}, {"name": "Ascorbic", "manufacturer": None}),
    ({"status": 1, "product": {"brands": "X"}}, None),
    ({"status": 0}, None),
])
def test_openfoodfacts_parsing(monkeypatch, payload, expected):
    fake_http(monkeypatch, httpx.Response(200, json=payload))
    assert lookup_openfoodfacts(GTIN) == expected


def test_openfoodfacts_errors_are_swallowed(monkeypatch):
    fake_http(monkeypatch, error=httpx.ConnectTimeout("timeout"))
    assert lookup_openfoodfacts(GTIN) is None
    fake_http(monkeypatch, httpx.Response(200, text="<html>not json</html>"))
    assert lookup_openfoodfacts(GTIN) is None
    fake_http(monkeypatch, httpx.Response(503, text="down"))
    assert lookup_openfoodfacts(GTIN) is None

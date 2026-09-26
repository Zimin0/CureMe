import httpx

from app import websearch
from app.lookup import guess_blister_size
from app.websearch import combine, parse_title

# Заголовки из реальной выдачи поисковика по коду 4605077018932.
LARINGOBAKT = [
    "Ларингобакт таблетки для рассасывания 20мг+10мг №30 | Аптека «Семейная»",
    "Ларингобакт таблетки купить в Санкт-Петербурге по цене от 267 руб., заказать с доставкой в аптеку, инструкция, 4605077018932",
    "Block 414166",
    "eo2018 suporg",
    "Ларингобакт таблетки для рассасывания 20 мг+10мг 30 шт - купить, цена и отзывы, инструкция по применению",
]


def test_combine_votes_across_pharmacies():
    p = combine(LARINGOBAKT)
    assert p.name == "Ларингобакт"
    assert p.form == "Таблетки для рассасывания"
    assert p.dosage == "20 мг + 10 мг"
    assert p.pack_size == 30 and p.unit == "таб"
    assert p.title == "Ларингобакт таблетки для рассасывания 20 мг + 10 мг №30"


def test_parse_various_titles():
    assert parse_title("Нурофен таб. п/о 200мг №10 - купить")["pack_size"] == 10
    n = parse_title("Називин Сенситив капли назальные 0,01% 5мл")
    assert n["name"] == "Називин Сенситив" and n["pack_size"] == 5 and n["unit"] == "мл"
    assert parse_title("Ибуклин Юниор таблетки диспергируемые 100мг+125мг N20")["dosage"] == "100 мг + 125 мг"
    assert parse_title("Купить лекарства недорого") is None


def test_blister_guess():
    assert guess_blister_size(30, "таб") == 10
    assert guess_blister_size(24, "таб") == 12
    assert guess_blister_size(5, "мл") is None


def test_search_engines_parse_html():
    ddg = ''.join(f'<a rel="nofollow" class="result__a" href="https://x{i}.ru">{t}</a>' for i, t in enumerate(LARINGOBAKT))
    bing = ''.join(f'<li class="b_algo"><h2><a href="https://y{i}.ru" h="ID">{t}</a></h2></li>' for i, t in enumerate(LARINGOBAKT))

    def handler(req: httpx.Request):
        return httpx.Response(200, text=ddg if "duckduckgo" in req.url.host else bing)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    for _, fn in websearch.ENGINES:
        hits = fn(client, "4605077018932")
        assert len(hits) == 5 and combine([t for t, _ in hits]).name == "Ларингобакт"


# --- дополнительные случаи -----------------------------------------------------

import pytest

from app.websearch import WebProduct, clean_title, search_barcode


@pytest.mark.parametrize("raw, clean", [
    ("<b>Нурофен</b> таблетки 200&nbsp;мг", "Нурофен таблетки 200 мг"),
    ("Нурофен таблетки | Аптека Ригла", "Нурофен таблетки"),
    ("Нурофен таблетки - купить в Москве", "Нурофен таблетки"),
    ("Нурофен таблетки: цена от 100 ₽", "Нурофен таблетки"),
    ("  Нурофен   таблетки  ", "Нурофен таблетки"),
])
def test_clean_title(raw, clean):
    assert clean_title(raw) == clean


@pytest.mark.parametrize("title, field, value", [
    ("Мирамистин раствор 0,01% 150мл", "pack_size", 150),
    ("Мирамистин раствор 0,01% 150мл", "unit", "мл"),
    ("Мирамистин раствор 0,01% 150мл", "dosage", "0.01 %"),
    ("Смекта порошок 3г пакетики №10", "pack_size", 10),
    ("Смекта порошок 3г пакетики №10", "form", "Порошок"),
    ("Виферон свечи 150000 МЕ №10", "unit", "шт"),
    ("Нурофен капсулы 200 мг 16 шт", "pack_size", 16),
    ("Нурофен Экспресс капсулы 200 mg №16", "dosage", "200 мг"),
    ("Ношпа табл. 40мг N 24", "pack_size", 24),
])
def test_parse_title_fields(title, field, value):
    assert parse_title(title)[field] == value


@pytest.mark.parametrize("title", [
    "таблетки от головы",                       # форма в самом начале — нет названия
    "Цена на 4605077018932 таблетки",           # мусор вместо названия
    "Каталог аптеки",                           # нет формы вовсе
])
def test_parse_title_rejects_non_products(title):
    assert parse_title(title) is None


def test_combine_returns_none_without_products():
    assert combine(["Каталог", "Главная страница"]) is None


def test_combine_keeps_source_urls_of_winning_name():
    titles = ["Нурофен таблетки 200мг №10", "Нурофен таблетки 200мг №10", "Ибупрофен таблетки 200мг №10"]
    p = combine(titles, ["a", "b", "c"])
    assert p.name == "Нурофен" and p.sources == ["a", "b"]


def test_search_barcode_falls_back_to_next_engine(monkeypatch):
    calls = []

    def broken(client, q):
        calls.append("ddg")
        raise httpx.ConnectError("нет сети")

    def empty(client, q):
        calls.append("empty")
        return [("Главная страница", "u")]

    def good(client, q):
        calls.append("good")
        return [(t, "u") for t in LARINGOBAKT]

    monkeypatch.setattr(websearch, "ENGINES", [("a", broken), ("b", empty), ("c", good)])
    p = search_barcode("4605077018932")
    assert isinstance(p, WebProduct) and p.name == "Ларингобакт"
    assert calls == ["ddg", "empty", "good"]


def test_search_barcode_all_engines_fail(monkeypatch):
    def broken(client, q):
        raise httpx.ReadTimeout("медленно")

    monkeypatch.setattr(websearch, "ENGINES", [("a", broken), ("b", broken)])
    assert search_barcode("4605077018932") is None


@pytest.mark.parametrize("pack, unit, blister", [
    (20, "таб", 10), (28, "таб", 14), (16, "капс", 8), (6, "шт", 6), (7, "таб", 7),
    (13, "таб", 13),             # простое число — один блистер на всю пачку
    (None, "таб", None), (10, "г", None),
])
def test_blister_guess_table(pack, unit, blister):
    assert guess_blister_size(pack, unit) == blister

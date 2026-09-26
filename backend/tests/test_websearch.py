from types import SimpleNamespace

import httpx

from app import lookup, websearch
from app.lookup import guess_blister_size
from app.websearch import combine, parse_title
from tests.conftest import register

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


def test_scan_unknown_code_goes_to_internet_and_is_cached(client, monkeypatch):
    calls = []

    def fake_search(ean):
        calls.append(ean)
        return combine(LARINGOBAKT)

    monkeypatch.setattr(lookup, "search_barcode", fake_search)
    monkeypatch.setattr(lookup, "get_settings", lambda: SimpleNamespace(remote_lookup=True))
    h, u = register(client)
    f = u["families"][0]["id"]
    r = client.post(f"/api/families/{f}/scan", headers=h, json={"raw": "4605077018932"}).json()
    assert r["product"]["name"] == "Ларингобакт"
    assert r["product"]["pack_size"] == 30 and r["product"]["blister_size"] == 10
    assert r["product"]["source"] == "internet"

    # второй раз (и в другой семье) — из справочника, без запроса в сеть
    h2, u2 = register(client, "b@example.com", "Б")
    r2 = client.post(f"/api/families/{u2['families'][0]['id']}/scan", headers=h2, json={"raw": "4605077018932"}).json()
    assert r2["product"]["title"].startswith("Ларингобакт") and calls == ["4605077018932"]

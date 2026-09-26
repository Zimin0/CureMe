"""Сквозной сценарий сканирования незнакомого кода: интернет → общий справочник."""

from types import SimpleNamespace

from app import lookup
from app.websearch import combine
from tests.conftest import register
from tests.unit.test_websearch import LARINGOBAKT


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

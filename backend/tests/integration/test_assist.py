"""Главная страница, подбор под болезнь, сканирование и справочник товаров."""

from datetime import date, timedelta

from app.codes import GS
from tests.conftest import register


def day(n: int) -> str:
    return str(date.today() + timedelta(days=n))


def add(client, h, f, **body):
    r = client.post(f"/api/families/{f}/medicines", headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_overview_buckets(client, owner):
    h, _, f = owner
    add(client, h, f, name="Годное", packages=[{"quantity": 5, "expiry_date": day(300)}, {"quantity": 1}])
    add(client, h, f, name="Скоро-2", packages=[{"quantity": 5, "expiry_date": day(20)}])
    add(client, h, f, name="Скоро-1", packages=[{"quantity": 5, "expiry_date": day(3)}])
    add(client, h, f, name="Просрочка", packages=[{"quantity": 1, "expiry_date": day(-1)}])
    fav = add(client, h, f, name="Пусто")
    client.put(f"/api/families/{f}/medicines/{fav['id']}/mark", headers=h, json={"is_favorite": True, "helps_me": True})

    ov = client.get(f"/api/families/{f}/overview", headers=h).json()
    assert ov["total_medicines"] == 5 and ov["total_packages"] == 5
    assert [m["name"] for m in ov["expiring"]] == ["Скоро-1", "Скоро-2"]  # ближайший срок первым
    assert [m["name"] for m in ov["expired"]] == ["Просрочка"]
    assert [m["name"] for m in ov["low"]] == ["Пусто"]
    assert [m["name"] for m in ov["favorites"]] == [m["name"] for m in ov["helps_me"]] == ["Пусто"]
    assert ov["expiring_soon_days"] == 30


def test_overview_of_empty_cabinet(client, owner):
    h, _, f = owner
    ov = client.get(f"/api/families/{f}/overview", headers=h).json()
    assert ov["total_medicines"] == 0 and ov["expired"] == []


def test_suggest_ranking_and_warnings(client, owner):
    h, _, f = owner
    add(client, h, f, name="Нурофен", indications="головная боль", contraindications="язва желудка",
        packages=[{"quantity": 10, "expiry_date": day(10)}])
    add(client, h, f, name="Цитрамон", indications="головная боль", packages=[])
    add(client, h, f, name="Пенталгин", indications="головная боль",
        packages=[{"quantity": 5, "expiry_date": day(300)}, {"quantity": 2, "expiry_date": day(-5)}])

    r = client.get(f"/api/families/{f}/suggest", headers=h, params={"condition": "головная боль"}).json()
    by_name = {x["medicine"]["name"]: x for x in r["results"]}
    assert r["results"][-1]["medicine"]["name"] == "Цитрамон"  # закончившееся уходит вниз
    assert "Закончилось" in by_name["Цитрамон"]["warnings"]
    assert "Противопоказания: язва желудка" in by_name["Нурофен"]["warnings"]
    assert "Срок истекает через 10 дн." in by_name["Нурофен"]["warnings"]
    assert "Есть просроченная упаковка — берите годную" in by_name["Пенталгин"]["warnings"]
    assert by_name["Нурофен"]["reasons"] == ["В показаниях: «головная боль»"]
    assert "не медицинский совет" in r["disclaimer"]


def test_suggest_only_expired_left(client, owner):
    h, _, f = owner
    add(client, h, f, name="Смекта", indications="диарея", packages=[{"quantity": 3, "expiry_date": day(-1)}])
    r = client.get(f"/api/families/{f}/suggest", headers=h, params={"condition": "диарея"}).json()
    assert r["results"][0]["warnings"] == ["Осталось только просроченное"]


def test_suggest_by_category_and_family_marks(client, owner):
    h1, _, f = owner
    cats = {c["name"]: c["id"] for c in client.get(f"/api/families/{f}/categories", headers=h1).json()}
    med = add(client, h1, f, name="Супрастин", category_id=cats["Аллергия"], packages=[{"quantity": 10}])
    code = client.get(f"/api/families/{f}", headers=h1).json()["invite_code"]
    h2, _ = register(client, "mom@example.com", "Мама", invite=code)
    client.put(f"/api/families/{f}/medicines/{med['id']}/mark", headers=h2, json={"helps_me": True})

    r = client.get(f"/api/families/{f}/suggest", headers=h1, params={"condition": "крапивница"}).json()
    assert r["results"][0]["reasons"] == ["Категория «Аллергия»", "Помогает: Мама"]


def test_suggest_validation(client, owner):
    h, _, f = owner
    url = f"/api/families/{f}/suggest"
    assert client.get(url, headers=h, params={"condition": "a"}).status_code == 422
    assert client.get(url, headers=h).status_code == 422
    assert client.get(url, headers=h, params={"condition": "x" * 101}).status_code == 422
    assert client.get(url, headers=h, params={"condition": "что-то редкое"}).json()["results"] == []


def test_scan_rejects_garbage(client, owner):
    h, _, f = owner
    assert client.post(f"/api/families/{f}/scan", headers=h, json={"raw": "hello"}).status_code == 422
    assert client.post(f"/api/families/{f}/scan", headers=h, json={"raw": ""}).status_code == 422


def test_scan_known_medicine_does_not_hit_internet(client, owner, monkeypatch):
    from app import lookup

    def boom(*a, **kw):
        raise AssertionError("в сеть ходить не должны")

    monkeypatch.setattr(lookup, "search_barcode", boom)
    h, _, f = owner
    med = add(client, h, f, name="Нурофен", gtin="4601669002013", blister_size=12)
    raw = f"0104601669002013215ABCDEFGHIJKL{GS}17270531"
    r = client.post(f"/api/families/{f}/scan", headers=h, json={"raw": raw}).json()
    assert r["medicine"]["id"] == med["id"] and r["duplicate_package"] is False
    assert r["display_code"] == "4601669002013"
    assert r["product"]["blister_size"] == 12


def test_products_endpoint(client, owner):
    h, _, f = owner
    assert client.get("/api/products/hello", headers=h).status_code == 422
    assert client.get("/api/products/4601669002013", headers=h).status_code == 404
    assert client.get("/api/products/4601669002013").status_code == 401

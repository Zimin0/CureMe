"""Лекарства, упаковки, личные отметки и фильтры списка."""

from datetime import date, timedelta

import pytest

from tests.conftest import register


def day(n: int) -> str:
    return str(date.today() + timedelta(days=n))


@pytest.fixture
def cabinet(client, owner):
    """Аптечка с набором лекарств во всех состояниях."""
    h, _, f = owner
    cats = {c["name"]: c["id"] for c in client.get(f"/api/families/{f}/categories", headers=h).json()}

    def add(**body):
        r = client.post(f"/api/families/{f}/medicines", headers=h, json=body)
        assert r.status_code == 201, r.text
        return r.json()

    meds = {
        "ok": add(name="Ибупрофен", active_ingredient="ибупрофен", manufacturer="Озон", indications="головная боль",
                  category_id=cats["Обезболивающие"], packages=[{"quantity": 20, "expiry_date": day(400)}]),
        "expiring": add(name="Називин", form="Капли", indications="насморк", packages=[{"quantity": 1, "expiry_date": day(5)}]),
        "expired": add(name="Смекта", indications="диарея", packages=[{"quantity": 3, "expiry_date": day(-2)}]),
        "low": add(name="Лоратадин", min_quantity=5, indications="аллергия", packages=[{"quantity": 2, "expiry_date": day(300)}]),
        "out": add(name="Бинт", packages=[]),
    }
    return h, f, meds


def names(r):
    return sorted(m["name"] for m in r.json())


def test_list_is_sorted_by_name(client, cabinet):
    h, f, _ = cabinet
    r = client.get(f"/api/families/{f}/medicines", headers=h)
    assert [m["name"] for m in r.json()] == ["Бинт", "Ибупрофен", "Лоратадин", "Називин", "Смекта"]


@pytest.mark.parametrize("flt, expected", [
    ("expired", ["Смекта"]),
    ("low", ["Бинт", "Лоратадин"]),
    ("attention", ["Бинт", "Лоратадин", "Називин", "Смекта"]),
])
def test_status_filters(client, cabinet, flt, expected):
    h, f, _ = cabinet
    assert names(client.get(f"/api/families/{f}/medicines", headers=h, params={"filter": flt})) == expected


def test_unknown_filter_is_rejected(client, cabinet):
    h, f, _ = cabinet
    assert client.get(f"/api/families/{f}/medicines", headers=h, params={"filter": "all"}).status_code == 422


def test_personal_filters_differ_between_members(client, cabinet):
    h1, f, meds = cabinet
    code = client.get(f"/api/families/{f}", headers=h1).json()["invite_code"]
    h2, _ = register(client, "mom@example.com", "Мама", invite=code)
    client.put(f"/api/families/{f}/medicines/{meds['ok']['id']}/mark", headers=h1, json={"is_favorite": True})
    client.put(f"/api/families/{f}/medicines/{meds['low']['id']}/mark", headers=h2, json={"helps_me": True})

    url = f"/api/families/{f}/medicines"
    assert names(client.get(url, headers=h1, params={"filter": "favorites"})) == ["Ибупрофен"]
    assert names(client.get(url, headers=h2, params={"filter": "favorites"})) == []
    assert names(client.get(url, headers=h2, params={"filter": "helps_me"})) == ["Лоратадин"]
    assert names(client.get(url, headers=h1, params={"filter": "helps_me"})) == []


@pytest.mark.parametrize("q, expected", [
    ("ибу", ["Ибупрофен"]),              # часть названия
    ("ОЗОН", ["Ибупрофен"]),             # производитель, без учёта регистра
    ("капли", ["Називин"]),              # форма
    ("головной боли", ["Ибупрофен"]),    # показания с другой формой слова
    ("обезболивающие", ["Ибупрофен"]),   # категория
    ("ничего такого", []),
])
def test_search(client, cabinet, q, expected):
    h, f, _ = cabinet
    assert names(client.get(f"/api/families/{f}/medicines", headers=h, params={"q": q})) == expected


def test_category_filter(client, cabinet):
    h, f, meds = cabinet
    cid = meds["ok"]["category_id"]
    assert names(client.get(f"/api/families/{f}/medicines", headers=h, params={"category_id": cid})) == ["Ибупрофен"]


def test_create_validation(client, owner):
    h, _, f = owner
    url = f"/api/families/{f}/medicines"
    assert client.post(url, headers=h, json={"name": ""}).status_code == 422
    assert client.post(url, headers=h, json={"name": "X", "min_quantity": -1}).status_code == 422
    assert client.post(url, headers=h, json={"name": "X", "blister_size": 0}).status_code == 422
    assert client.post(url, headers=h, json={"name": "X", "packages": [{"quantity": -1}]}).status_code == 422
    assert client.post(url, headers=h, json={"name": "X", "packages": [{"expiry_date": "31.05.2027"}]}).status_code == 422


def test_gtin_is_normalized_and_remembered(client, owner):
    h, _, f = owner
    url = f"/api/families/{f}/medicines"
    assert client.post(url, headers=h, json={"name": "X", "gtin": "123"}).status_code == 400
    m = client.post(url, headers=h, json={"name": "Нурофен", "dosage": "200 мг", "gtin": "4601669002013"}).json()
    assert m["gtin"] == "04601669002013"
    # код попал в общий справочник
    p = client.get("/api/products/4601669002013", headers=h).json()
    assert (p["name"], p["dosage"], p["source"]) == ("Нурофен", "200 мг", "user")


def test_update_is_partial(client, cabinet):
    h, f, meds = cabinet
    url = f"/api/families/{f}/medicines/{meds['ok']['id']}"
    m = client.patch(url, headers=h, json={"notes": "после еды", "name": None}).json()
    assert m["name"] == "Ибупрофен" and m["notes"] == "после еды"
    assert m["indications"] == "головная боль"  # не трогали — не изменилось
    # явный null очищает категорию и порог
    m = client.patch(url, headers=h, json={"category_id": None, "min_quantity": None}).json()
    assert m["category_id"] is None and m["min_quantity"] is None
    assert client.patch(url, headers=h, json={"gtin": "abc"}).status_code == 400
    assert client.patch(url, headers=h, json={"category_id": 999999}).status_code == 400


def test_delete(client, cabinet):
    h, f, meds = cabinet
    url = f"/api/families/{f}/medicines/{meds['ok']['id']}"
    assert client.delete(url, headers=h).status_code == 204
    assert client.get(url, headers=h).status_code == 404
    assert client.delete(url, headers=h).status_code == 404


def test_packages_lifecycle(client, cabinet):
    h, f, meds = cabinet
    url = f"/api/families/{f}/medicines/{meds['low']['id']}/packages"
    m = client.post(url, headers=h, json={"quantity": 10, "expiry_date": day(200), "serial": "S1", "location": "кухня"})
    assert m.status_code == 201
    m = m.json()
    assert m["stock"]["total"] == 12 and m["stock"]["status"] == "ok"
    # пакеты отсортированы по сроку годности
    assert [p["expiry_date"] for p in m["packages"]] == sorted(p["expiry_date"] for p in m["packages"])

    assert client.post(url, headers=h, json={"quantity": 1, "serial": "S1"}).status_code == 409

    new = next(p for p in m["packages"] if p["serial"] == "S1")
    m = client.patch(f"{url}/{new['id']}", headers=h, json={"quantity": 4, "location": "дача"}).json()
    changed = next(p for p in m["packages"] if p["id"] == new["id"])
    assert (changed["quantity"], changed["location"], changed["serial"]) == (4, "дача", "S1")
    assert client.patch(f"{url}/{new['id']}", headers=h, json={"quantity": -1}).status_code == 422

    m = client.delete(f"{url}/{new['id']}", headers=h).json()
    assert m["stock"]["total"] == 2
    assert client.delete(f"{url}/{new['id']}", headers=h).status_code == 404


def test_package_days_left_and_expired_flags(client, cabinet):
    h, f, meds = cabinet
    m = client.get(f"/api/families/{f}/medicines/{meds['expired']['id']}", headers=h).json()
    assert m["packages"][0]["expired"] is True and m["packages"][0]["days_left"] == -2


def test_consume(client, cabinet):
    h, f, meds = cabinet
    base = f"/api/families/{f}/medicines"
    m = client.post(f"{base}/{meds['ok']['id']}/consume", headers=h, json={"amount": 1.5}).json()
    assert m["stock"]["total"] == 18.5 and m["packages"][0]["opened_at"] == str(date.today())
    assert client.post(f"{base}/{meds['ok']['id']}/consume", headers=h, json={}).json()["stock"]["total"] == 17.5
    assert client.post(f"{base}/{meds['ok']['id']}/consume", headers=h, json={"amount": 0}).status_code == 422
    # только просроченное или пусто — списывать нечего
    assert client.post(f"{base}/{meds['expired']['id']}/consume", headers=h, json={"amount": 1}).status_code == 400
    assert client.post(f"{base}/{meds['out']['id']}/consume", headers=h, json={"amount": 1}).status_code == 400
    # списать больше, чем есть, можно — остаток станет нулём
    assert client.post(f"{base}/{meds['low']['id']}/consume", headers=h, json={"amount": 10}).json()["stock"]["status"] == "out"


def test_mark_is_merged_not_replaced(client, cabinet):
    h, f, meds = cabinet
    url = f"/api/families/{f}/medicines/{meds['ok']['id']}/mark"
    client.put(url, headers=h, json={"is_favorite": True, "personal_note": "мне 1 таблетку"})
    m = client.put(url, headers=h, json={"helps_me": True}).json()
    assert (m["is_favorite"], m["helps_me"], m["personal_note"]) == (True, True, "мне 1 таблетку")
    m = client.put(url, headers=h, json={"is_favorite": False}).json()
    assert (m["is_favorite"], m["helps_me"]) == (False, True)

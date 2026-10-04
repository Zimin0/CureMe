from datetime import date, timedelta

from app.codes import GS
from tests.conftest import register


def fid(user):
    return user["families"][0]["id"]


def test_register_creates_family_with_categories(client):
    h, user = register(client)
    assert user["families"][0]["role"] == "owner"
    cats = client.get(f"/api/families/{fid(user)}/categories", headers=h).json()
    assert len(cats) >= 10


def test_family_invite_and_shared_cabinet_with_personal_marks(client):
    h1, u1 = register(client)
    f = fid(u1)
    code = client.get(f"/api/families/{f}", headers=h1).json()["invite_code"]
    assert client.get(f"/api/invites/{code}").json()["family_name"] == "Семья Никита"

    h2, u2 = register(client, "mom@example.com", "Мама", invite=code)
    assert fid(u2) == f and u2["families"][0]["role"] == "member"

    med = client.post(f"/api/families/{f}/medicines", headers=h1, json={"name": "Нурофен"}).json()
    # второй участник видит лекарство и отмечает его для себя
    client.put(f"/api/families/{f}/medicines/{med['id']}/mark", headers=h2, json={"helps_me": True, "is_favorite": True})
    mine = client.get(f"/api/families/{f}/medicines/{med['id']}", headers=h2).json()
    theirs = client.get(f"/api/families/{f}/medicines/{med['id']}", headers=h1).json()
    assert mine["helps_me"] and mine["is_favorite"]
    assert not theirs["helps_me"] and theirs["helps_members"] == ["Мама"]

    # участник не может удалять других, владелец может
    assert client.delete(f"/api/families/{f}/members/{u1['id']}", headers=h2).status_code == 403
    assert client.delete(f"/api/families/{f}/members/{u2['id']}", headers=h1).status_code == 204
    assert client.get(f"/api/families/{f}/medicines", headers=h2).status_code == 404


def test_stock_expiry_and_consume(client):
    h, u = register(client)
    f = fid(u)
    today = date.today()
    med = client.post(f"/api/families/{f}/medicines", headers=h, json={
        "name": "Парацетамол", "unit": "таб", "min_quantity": 5,
        "packages": [
            {"quantity": 10, "expiry_date": str(today + timedelta(days=400))},
            {"quantity": 4, "expiry_date": str(today + timedelta(days=10))},
            {"quantity": 6, "expiry_date": str(today - timedelta(days=3))},
        ],
    }).json()
    assert med["stock"]["total"] == 14
    assert med["stock"]["expired_quantity"] == 6
    assert med["stock"]["status"] == "expired"

    # списываем 5: сначала из упаковки, что истекает раньше (4), затем 1 из следующей
    med = client.post(f"/api/families/{f}/medicines/{med['id']}/consume", headers=h, json={"amount": 5}).json()
    qty = sorted(p["quantity"] for p in med["packages"] if not p["expired"])
    assert qty == [0, 9]

    ov = client.get(f"/api/families/{f}/overview", headers=h).json()
    assert [m["name"] for m in ov["expired"]] == ["Парацетамол"]


def test_suggest_by_condition(client):
    h, u = register(client)
    f = fid(u)
    cats = {c["name"]: c["id"] for c in client.get(f"/api/families/{f}/categories", headers=h).json()}
    future = str(date.today() + timedelta(days=300))
    ibu = client.post(f"/api/families/{f}/medicines", headers=h, json={
        "name": "Ибупрофен", "indications": "головная боль, зубная боль, температура",
        "category_id": cats["Обезболивающие"], "packages": [{"quantity": 10, "expiry_date": future}],
    }).json()
    client.post(f"/api/families/{f}/medicines", headers=h, json={
        "name": "Цитрамон", "indications": "мигрень", "packages": [{"quantity": 10, "expiry_date": future}],
    })
    client.post(f"/api/families/{f}/medicines", headers=h, json={
        "name": "Смекта", "indications": "диарея, отравление", "packages": [{"quantity": 5}],
    })
    r = client.get(f"/api/families/{f}/suggest", params={"condition": "болит голова"}, headers=h).json()
    names = [x["medicine"]["name"] for x in r["results"]]
    assert "Ибупрофен" in names and "Цитрамон" in names and "Смекта" not in names

    client.put(f"/api/families/{f}/medicines/{ibu['id']}/mark", headers=h, json={"helps_me": True})
    r = client.get(f"/api/families/{f}/suggest", params={"condition": "мигрень"}, headers=h).json()
    assert r["results"][0]["medicine"]["name"] == "Ибупрофен"
    assert r["results"][0]["reasons"][0] == "Вам помогает"

    r = client.get(f"/api/families/{f}/suggest", params={"condition": "понос"}, headers=h).json()
    assert [x["medicine"]["name"] for x in r["results"]] == ["Смекта"]


def test_scan_flow(client):
    h, u = register(client)
    f = fid(u)
    raw = f"0104601669002013211ABCDEFGHIJKL{GS}17270531{GS}10AB1234{GS}91EE06{GS}92abc="
    r = client.post(f"/api/families/{f}/scan", headers=h, json={"raw": raw}).json()
    assert r["medicine"] is None and r["parsed"]["expiry"] == "2027-05-31"

    med = client.post(f"/api/families/{f}/medicines", headers=h, json={
        "name": "Нурофен", "gtin": r["parsed"]["gtin"],
        "packages": [{"quantity": 1, "expiry_date": "2027-05-31", "serial": r["parsed"]["serial"]}],
    }).json()

    # тот же товар по обычному штрихкоду находится в аптечке, а та же упаковка помечается дублем
    r2 = client.post(f"/api/families/{f}/scan", headers=h, json={"raw": "4601669002013"}).json()
    assert r2["medicine"]["id"] == med["id"]
    r3 = client.post(f"/api/families/{f}/scan", headers=h, json={"raw": raw}).json()
    assert r3["duplicate_package"] is True

    # другая семья правок этой семьи не видит: общий справочник пополняется только из интернета
    h2, u2 = register(client, "other@example.com", "Сосед")
    r4 = client.post(f"/api/families/{fid(u2)}/scan", headers=h2, json={"raw": "4601669002013"}).json()
    assert r4["medicine"] is None and r4["product"] is None


def test_other_family_is_isolated(client):
    h1, u1 = register(client)
    h2, _ = register(client, "stranger@example.com", "Чужой")
    assert client.get(f"/api/families/{fid(u1)}/medicines", headers=h2).status_code == 404

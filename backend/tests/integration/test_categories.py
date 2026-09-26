"""Категории аптечки."""

from tests.conftest import fid, register


def test_crud(client, owner):
    h, _, f = owner
    url = f"/api/families/{f}/categories"
    before = client.get(url, headers=h).json()
    assert [c["name"] for c in before][:2] == ["Обезболивающие", "Жаропонижающие"]

    c = client.post(url, headers=h, json={"name": "Для кота", "icon": "🐱", "color": "#123456"})
    assert c.status_code == 201
    c = c.json()
    listed = client.get(url, headers=h).json()
    assert listed[-1]["id"] == c["id"]  # новая категория идёт последней

    upd = client.put(f"{url}/{c['id']}", headers=h, json={"name": "Для собаки", "icon": "🐶", "color": "#654321"}).json()
    assert (upd["name"], upd["icon"]) == ("Для собаки", "🐶")

    assert client.delete(f"{url}/{c['id']}", headers=h).status_code == 204
    assert len(client.get(url, headers=h).json()) == len(before)
    assert client.delete(f"{url}/{c['id']}", headers=h).status_code == 404


def test_validation(client, owner):
    h, _, f = owner
    url = f"/api/families/{f}/categories"
    assert client.post(url, headers=h, json={"name": ""}).status_code == 422
    assert client.post(url, headers=h, json={"name": "x" * 61}).status_code == 422
    assert client.post(url, headers=h, json={"name": "Без иконки"}).json()["icon"] == "💊"


def test_medicine_count_and_delete_keeps_medicines(client, owner):
    h, _, f = owner
    url = f"/api/families/{f}/categories"
    cat = client.post(url, headers=h, json={"name": "Глаза"}).json()
    med = client.post(f"/api/families/{f}/medicines", headers=h, json={"name": "Тауфон", "category_id": cat["id"]}).json()
    counts = {c["id"]: c["medicine_count"] for c in client.get(url, headers=h).json()}
    assert counts[cat["id"]] == 1

    client.delete(f"{url}/{cat['id']}", headers=h)
    m = client.get(f"/api/families/{f}/medicines/{med['id']}", headers=h).json()
    assert m["category_id"] is None and m["category"] is None


def test_foreign_category_is_invisible(client, owner):
    h1, _, f1 = owner
    h2, u2 = register(client, "other@example.com", "Сосед")
    foreign = client.get(f"/api/families/{fid(u2)}/categories", headers=h2).json()[0]["id"]
    assert client.put(f"/api/families/{f1}/categories/{foreign}", headers=h1, json={"name": "x"}).status_code == 404
    assert client.delete(f"/api/families/{f1}/categories/{foreign}", headers=h1).status_code == 404
    # и её нельзя присвоить своему лекарству
    r = client.post(f"/api/families/{f1}/medicines", headers=h1, json={"name": "X", "category_id": foreign})
    assert r.status_code == 400

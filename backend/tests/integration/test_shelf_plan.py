"""Схема полок аптечки и место лекарства на ней («Где лежит»)."""

from tests.conftest import register


def test_plan_and_place(client, owner):
    h, _, f = owner
    url = f"/api/families/{f}/shelf-plan"
    assert client.get(url, headers=h).json()["shelves"] == []
    plan = {"shelves": [{"id": "s1", "name": "Верхняя", "x": 0.05, "y": 0.05, "w": 0.9, "h": 0.3}], "height": 0.8}
    assert client.put(url, headers=h, json=plan).json()["shelves"][0]["name"] == "Верхняя"
    assert client.get(url, headers=h).json()["height"] == 0.8

    med = client.post(f"/api/families/{f}/medicines", headers=h, json={"name": "Х"}).json()
    assert med["place_x"] is None
    mu = f"/api/families/{f}/medicines/{med['id']}"
    r = client.patch(mu, headers=h, json={"place_x": 0.4, "place_y": 0.2, "place_r": 0.08})
    assert (r.json()["place_x"], r.json()["place_r"]) == (0.4, 0.08)
    # частичная метка не сохраняется
    r = client.patch(mu, headers=h, json={"place_x": None})
    assert r.json()["place_y"] is None and r.json()["place_r"] is None
    assert client.patch(mu, headers=h, json={"place_x": 2}).status_code == 422


def test_plan_validation_and_access(client, owner):
    h, _, f = owner
    url = f"/api/families/{f}/shelf-plan"
    dup = {"shelves": [{"id": "a", "x": 0, "y": 0, "w": 1, "h": 1}] * 2}
    assert client.put(url, headers=h, json=dup).status_code == 400
    assert client.put(url, headers=h, json={"shelves": [{"id": "a", "x": 0, "y": 0, "w": 0, "h": 1}]}).status_code == 422
    other, _ = register(client, "stranger@example.com")
    assert client.get(url, headers=other).status_code in (403, 404)


def test_box_kind(client, owner):
    h, _, f = owner
    url = f"/api/families/{f}/shelf-plan"
    plan = {"shelves": [{"id": "a", "x": 0, "y": 0, "w": 1, "h": 0.5}, {"id": "b", "name": "Таблетки", "kind": "box", "x": 0.1, "y": 0.1, "w": 0.3, "h": 0.2}]}
    out = client.put(url, headers=h, json=plan).json()
    assert [s["kind"] for s in out["shelves"]] == ["shelf", "box"]
    bad = {"shelves": [{"id": "a", "kind": "drawer", "x": 0, "y": 0, "w": 1, "h": 1}]}
    assert client.put(url, headers=h, json=bad).status_code == 422



def test_plus_only_when_billing_on(client, owner):
    from tests.integration.test_cabinet_ops import enable_billing

    h, _, f = owner
    med = client.post(f"/api/families/{f}/medicines", headers=h, json={"name": "Х"}).json()
    mu = f"/api/families/{f}/medicines/{med['id']}"
    enable_billing(client, h)
    r = client.put(f"/api/families/{f}/shelf-plan", headers=h, json={"shelves": []})
    assert r.status_code == 402 and r.headers["X-Plus-Feature"] == "shelf_plan"
    r = client.patch(mu, headers=h, json={"place_x": 0.4, "place_y": 0.2, "place_r": 0.08})
    assert r.status_code == 402 and r.headers["X-Plus-Feature"] == "shelf_plan"
    # убрать метку можно и без Плюса, схему смотреть тоже
    assert client.patch(mu, headers=h, json={"place_x": None, "place_y": None, "place_r": None}).status_code == 200
    assert client.get(f"/api/families/{f}/shelf-plan", headers=h).status_code == 200

from tests.conftest import register


def test_first_account_is_admin_and_others_are_not(client):
    admin, me = register(client)
    assert me["is_admin"] is True
    user, other = register(client, "masha@example.com", "Маша")
    assert other["is_admin"] is False
    assert client.get("/api/admin/users", headers=user).status_code == 403
    assert client.get("/api/admin/stats", headers=admin).json()["users"] == 2


def test_categories_are_shared_and_only_admin_changes_them(client):
    admin, a = register(client)
    user, b = register(client, "masha@example.com", "Маша")
    fam_a, fam_b = a["families"][0]["id"], b["families"][0]["id"]
    names = lambda h, f: [c["name"] for c in client.get(f"/api/families/{f}/categories", headers=h).json()]  # noqa: E731
    assert names(admin, fam_a) == names(user, fam_b) and len(names(admin, fam_a)) == 12

    # обычный участник категории менять не может
    assert client.post(f"/api/families/{fam_b}/categories", headers=user, json={"name": "Глаза"}).status_code == 405
    assert client.post("/api/admin/categories", headers=user, json={"name": "Глаза"}).status_code == 403

    r = client.post("/api/admin/categories", headers=admin, json={"name": "  Глаза ", "icon": "👁️"})
    assert r.status_code == 201 and r.json()["name"] == "Глаза"
    assert "Глаза" in names(user, fam_b)
    assert client.post("/api/admin/categories", headers=admin, json={"name": "глаза"}).status_code == 409

    # лекарство второй семьи с новой категорией; счётчик в семье — свой, в админке — общий
    cid = r.json()["id"]
    client.post(f"/api/families/{fam_b}/medicines", headers=user, json={"name": "Тауфон", "category_id": cid})
    count = lambda h, f: next(c["medicine_count"] for c in client.get(f"/api/families/{f}/categories", headers=h).json() if c["id"] == cid)  # noqa: E731
    assert count(user, fam_b) == 1 and count(admin, fam_a) == 0
    assert next(c for c in client.get("/api/admin/categories", headers=admin).json() if c["id"] == cid)["medicine_count"] == 1

    ids = [c["id"] for c in client.get("/api/admin/categories", headers=admin).json()]
    order = client.put("/api/admin/categories/order", headers=admin, json={"ids": [cid] + [i for i in ids if i != cid]}).json()
    assert order[0]["id"] == cid

    assert client.delete(f"/api/admin/categories/{cid}", headers=admin).status_code == 204
    med = client.get(f"/api/families/{fam_b}/medicines", headers=user).json()[0]
    assert med["category"] is None


def test_indication_hints_are_shared_and_only_admin_changes_them(client):
    admin, _ = register(client)
    user, _ = register(client, "masha@example.com", "Маша")
    hints = lambda h: client.get("/api/indication-hints", headers=h).json()  # noqa: E731
    # пока администратор ничего не менял — стандартный список
    assert hints(user)[:3] == ["головная боль", "температура", "простуда"] and len(hints(user)) == 12

    assert client.put("/api/admin/indication-hints", headers=user, json={"hints": ["x"]}).status_code == 403
    r = client.put("/api/admin/indication-hints", headers=admin,
                   json={"hints": ["  зубная   боль ", "Кашель", "", "кашель", "насморк"]})
    assert r.status_code == 200
    # пробелы схлопнуты, пустые и повторы (без учёта регистра) убраны, порядок сохранён
    assert r.json() == ["зубная боль", "Кашель", "насморк"]
    assert hints(user) == ["зубная боль", "Кашель", "насморк"]
    assert client.get("/api/admin/indication-hints", headers=admin).json() == hints(user)

    # пустой список — это тоже выбор администратора, стандартные подсказки не возвращаются
    client.put("/api/admin/indication-hints", headers=admin, json={"hints": []})
    assert hints(user) == []

    too_long = client.put("/api/admin/indication-hints", headers=admin, json={"hints": ["я" * 61]})
    assert too_long.status_code == 422
    too_many = client.put("/api/admin/indication-hints", headers=admin, json={"hints": [f"h{i}" for i in range(51)]})
    assert too_many.status_code == 422


def test_admin_manages_users(client):
    admin, me = register(client)
    _, masha = register(client, "masha@example.com", "Маша")

    r = client.patch(f"/api/admin/users/{masha['id']}", headers=admin, json={"is_admin": True, "name": "Мария"})
    assert r.json()["is_admin"] is True and r.json()["name"] == "Мария"
    assert client.patch(f"/api/admin/users/{me['id']}", headers=admin, json={"is_admin": False}).status_code == 400
    assert client.patch(f"/api/admin/users/{masha['id']}", headers=admin, json={"email": "NIKITA@example.com"}).status_code == 409

    client.patch(f"/api/admin/users/{masha['id']}", headers=admin, json={"password": "new-pass-phrase-77"})
    assert client.post("/api/auth/login", json={"email": "masha@example.com", "password": "new-pass-phrase-77"}).status_code == 200

    assert client.delete(f"/api/admin/users/{me['id']}", headers=admin).status_code == 400
    assert client.delete(f"/api/admin/users/{masha['id']}", headers=admin).status_code == 204
    users = client.get("/api/admin/users", headers=admin).json()
    assert [u["email"] for u in users] == ["nikita@example.com"]
    # семья Маши была только её — её тоже нет
    assert len(client.get("/api/admin/families", headers=admin).json()) == 1


def test_deleting_owner_passes_family_to_next_member(client):
    admin, _ = register(client)
    owner_h, owner = register(client, "owner@example.com", "Папа")
    code = client.get(f"/api/families/{owner['families'][0]['id']}", headers=owner_h).json()["invite_code"]
    kid_h, kid = register(client, "kid@example.com", "Сын", invite=code)

    client.delete(f"/api/admin/users/{owner['id']}", headers=admin)
    fam = client.get(f"/api/families/{owner['families'][0]['id']}", headers=kid_h).json()
    assert [(m["name"], m["role"]) for m in fam["members"]] == [("Сын", "owner")]


def test_admin_manages_families(client):
    admin, me = register(client)
    _, masha = register(client, "masha@example.com", "Маша")
    fid = masha["families"][0]["id"]

    r = client.post(f"/api/admin/families/{fid}/members", headers=admin, json={"email": "nikita@example.com"})
    assert [m["name"] for m in r.json()["members"]] == ["Маша", "Никита"]
    assert client.post(f"/api/admin/families/{fid}/members", headers=admin, json={"email": "nobody@example.com"}).status_code == 404

    # владелец один (R02): понизить единственного нельзя, владелец меняется назначением другого
    assert client.patch(f"/api/admin/families/{fid}/members/{masha['id']}", headers=admin, json={"role": "member"}).status_code == 400
    client.patch(f"/api/admin/families/{fid}/members/{me['id']}", headers=admin, json={"role": "owner"})
    assert client.patch(f"/api/admin/families/{fid}/members/{masha['id']}", headers=admin, json={"role": "member"}).status_code == 200

    assert client.patch(f"/api/admin/families/{fid}", headers=admin, json={"name": "Дача"}).json()["name"] == "Дача"
    assert client.delete(f"/api/admin/families/{fid}/members/{masha['id']}", headers=admin).status_code == 204
    fams = {f["id"]: f for f in client.get("/api/admin/families", headers=admin).json()}
    # Маша создала эту аптечку и уходит с ней (R09), а у оставшегося Никиты появляется пустая
    assert [m["name"] for m in fams[fid]["members"]] == ["Маша"]
    assert sorted(f["id"] for f in fams.values() if [m["name"] for m in f["members"]] == ["Никита"]) != []

    assert client.delete(f"/api/admin/families/{fid}", headers=admin).status_code == 204
    assert fid not in {f["id"] for f in client.get("/api/admin/families", headers=admin).json()}


def test_admin_emails_setting_grants_admin(client, monkeypatch):
    register(client)
    h, masha = register(client, "masha@example.com", "Маша")
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "admin_emails", ["Masha@Example.com"])
    assert client.get("/api/auth/me", headers=h).json()["is_admin"] is True


# --- дополнительные случаи -----------------------------------------------------

import os

import pytest

from app.config import get_settings

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 32


@pytest.mark.parametrize("body", [
    {"name": ""}, {"name": "x" * 61}, {},
    {"name": "Глаза", "color": "red"}, {"name": "Глаза", "color": "#12345"}, {"name": "Глаза", "icon": ""},
])
def test_category_validation(client, body):
    admin, _ = register(client)
    assert client.post("/api/admin/categories", headers=admin, json=body).status_code == 422


def test_category_rename_checks_duplicates_but_allows_own_name(client):
    admin, _ = register(client)
    cats = client.get("/api/admin/categories", headers=admin).json()
    first, second = cats[0], cats[1]
    url = f"/api/admin/categories/{first['id']}"
    assert client.put(url, headers=admin, json={"name": second["name"].upper()}).status_code == 409
    r = client.put(url, headers=admin, json={"name": f"  {first['name']}  ", "icon": "💉"})
    assert r.status_code == 200 and (r.json()["name"], r.json()["icon"]) == (first["name"], "💉")
    assert client.put("/api/admin/categories/99999", headers=admin, json={"name": "X"}).status_code == 404


def test_partial_reorder_keeps_the_rest_after(client):
    admin, _ = register(client)
    ids = [c["id"] for c in client.get("/api/admin/categories", headers=admin).json()]
    order = client.put("/api/admin/categories/order", headers=admin, json={"ids": [ids[-1], ids[-2]]}).json()
    assert [c["id"] for c in order][:2] == [ids[-1], ids[-2]]
    assert sorted(c["id"] for c in order) == sorted(ids)


def test_deleting_family_removes_photos(client):
    admin, _ = register(client)
    h, u = register(client, "masha@example.com", "Маша")
    f = u["families"][0]["id"]
    med = client.post(f"/api/families/{f}/medicines", headers=h, json={"name": "Нурофен"}).json()
    photo = client.put(f"/api/families/{f}/medicines/{med['id']}/photo", headers=h,
                       files={"file": ("p.jpg", JPEG, "image/jpeg")}).json()["photo_url"]
    path = get_settings().media_dir / photo.rsplit("/", 1)[1]
    assert os.path.exists(path)
    assert client.delete(f"/api/admin/families/{f}", headers=admin).status_code == 204
    assert not os.path.exists(path)
    assert client.get("/api/auth/me", headers=h).json()["families"] == []


def test_stats(client):
    admin, _ = register(client)
    h, u = register(client, "masha@example.com", "Маша")
    client.post(f"/api/families/{u['families'][0]['id']}/medicines", headers=h, json={"name": "Нурофен"})
    assert client.get("/api/admin/stats", headers=admin).json() == {
        "users": 2, "admins": 1, "families": 2, "medicines": 1, "categories": 12,
    }

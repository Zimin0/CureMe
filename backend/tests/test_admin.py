from .conftest import register


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


def test_admin_manages_users(client):
    admin, me = register(client)
    _, masha = register(client, "masha@example.com", "Маша")

    r = client.patch(f"/api/admin/users/{masha['id']}", headers=admin, json={"is_admin": True, "name": "Мария"})
    assert r.json()["is_admin"] is True and r.json()["name"] == "Мария"
    assert client.patch(f"/api/admin/users/{me['id']}", headers=admin, json={"is_admin": False}).status_code == 400
    assert client.patch(f"/api/admin/users/{masha['id']}", headers=admin, json={"email": "NIKITA@example.com"}).status_code == 409

    client.patch(f"/api/admin/users/{masha['id']}", headers=admin, json={"password": "newpass1"})
    assert client.post("/api/auth/login", json={"email": "masha@example.com", "password": "newpass1"}).status_code == 200

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

    assert client.patch(f"/api/admin/families/{fid}/members/{masha['id']}", headers=admin, json={"role": "member"}).status_code == 400
    client.patch(f"/api/admin/families/{fid}/members/{me['id']}", headers=admin, json={"role": "owner"})
    assert client.patch(f"/api/admin/families/{fid}/members/{masha['id']}", headers=admin, json={"role": "member"}).status_code == 200

    assert client.patch(f"/api/admin/families/{fid}", headers=admin, json={"name": "Дача"}).json()["name"] == "Дача"
    assert client.delete(f"/api/admin/families/{fid}/members/{masha['id']}", headers=admin).status_code == 204
    fams = {f["id"]: f for f in client.get("/api/admin/families", headers=admin).json()}
    assert [m["name"] for m in fams[fid]["members"]] == ["Никита"]

    assert client.delete(f"/api/admin/families/{fid}", headers=admin).status_code == 204
    assert fid not in {f["id"] for f in client.get("/api/admin/families", headers=admin).json()}


def test_admin_emails_setting_grants_admin(client, monkeypatch):
    register(client)
    h, masha = register(client, "masha@example.com", "Маша")
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "admin_emails", ["Masha@Example.com"])
    assert client.get("/api/auth/me", headers=h).json()["is_admin"] is True

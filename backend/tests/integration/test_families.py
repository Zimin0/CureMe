"""Семьи: приглашения, роли, выход из семьи."""

from tests.conftest import fid, register


def invite_code(client, h, family_id):
    return client.get(f"/api/families/{family_id}", headers=h).json()["invite_code"]


def two_members(client):
    h1, u1 = register(client)
    f = fid(u1)
    h2, u2 = register(client, "mom@example.com", "Мама", invite=invite_code(client, h1, f))
    return (h1, u1), (h2, u2), f


def test_create_second_family_with_default_categories(client, owner):
    h, _, first = owner
    r = client.post("/api/families", headers=h, json={"name": "  Дача "})
    assert r.status_code == 201
    fam = r.json()
    assert fam["name"] == "Дача" and fam["role"] == "owner" and fam["id"] != first
    assert len(client.get(f"/api/families/{fam['id']}/categories", headers=h).json()) == 12
    assert [f["name"] for f in client.get("/api/auth/me", headers=h).json()["families"]] == ["Семья Никита", "Дача"]


def test_invite_info_is_public(client, owner):
    h, _, f = owner
    code = invite_code(client, h, f)
    assert client.get(f"/api/invites/{code.lower()}").json() == {"family_name": "Семья Никита", "members": 1}
    assert client.get("/api/invites/UNKNOWN1").status_code == 404


def test_rename_and_regenerate_invite_are_owner_only(client):
    (h1, _), (h2, _), f = two_members(client)
    assert client.patch(f"/api/families/{f}", headers=h2, json={"name": "Моя"}).status_code == 403
    assert client.post(f"/api/families/{f}/invite", headers=h2).status_code == 403

    assert client.patch(f"/api/families/{f}", headers=h1, json={"name": "Зимины"}).json()["name"] == "Зимины"
    old = invite_code(client, h1, f)
    new = client.post(f"/api/families/{f}/invite", headers=h1).json()["invite_code"]
    assert new != old
    assert client.get(f"/api/invites/{old}").status_code == 404


def test_members_are_listed_owner_first(client):
    (h1, _), (h2, _), f = two_members(client)
    fam = client.get(f"/api/families/{f}", headers=h2).json()
    assert fam["role"] == "member"
    assert [(m["name"], m["role"]) for m in fam["members"]] == [("Никита", "owner"), ("Мама", "member")]


def test_add_member_by_email(client, owner):
    h, _, f = owner
    assert client.post(f"/api/families/{f}/members", headers=h, json={"email": "ghost@example.com"}).status_code == 404
    register(client, "dad@example.com", "Папа")
    fam = client.post(f"/api/families/{f}/members", headers=h, json={"email": "DAD@example.com"}).json()
    assert [m["name"] for m in fam["members"]] == ["Никита", "Папа"]
    assert client.post(f"/api/families/{f}/members", headers=h, json={"email": "dad@example.com"}).status_code == 409


def test_member_cannot_add_members(client):
    _, (h2, _), f = two_members(client)
    register(client, "dad@example.com", "Папа")
    assert client.post(f"/api/families/{f}/members", headers=h2, json={"email": "dad@example.com"}).status_code == 403


def test_roles(client):
    (h1, u1), (h2, u2), f = two_members(client)
    url = f"/api/families/{f}/members"
    # единственного владельца нельзя понизить
    assert client.patch(f"{url}/{u1['id']}", headers=h1, json={"role": "member"}).status_code == 400
    assert client.patch(f"{url}/{u2['id']}", headers=h1, json={"role": "admin"}).status_code == 422
    assert client.patch(f"{url}/99999", headers=h1, json={"role": "owner"}).status_code == 404
    # назначаем второго владельца — теперь первого понизить можно
    assert client.patch(f"{url}/{u2['id']}", headers=h1, json={"role": "owner"}).status_code == 200
    r = client.patch(f"{url}/{u1['id']}", headers=h2, json={"role": "member"})
    assert r.status_code == 200
    assert {m["name"]: m["role"] for m in r.json()["members"]} == {"Никита": "member", "Мама": "owner"}
    # и бывший владелец больше не может управлять ролями
    assert client.patch(f"{url}/{u2['id']}", headers=h1, json={"role": "member"}).status_code == 403


def test_member_can_leave(client):
    (h1, _), (h2, u2), f = two_members(client)
    assert client.delete(f"/api/families/{f}/members/{u2['id']}", headers=h2).status_code == 204
    assert client.get("/api/auth/me", headers=h2).json()["families"] == []
    assert len(client.get(f"/api/families/{f}", headers=h1).json()["members"]) == 1


def test_only_owner_cannot_leave_while_others_stay(client):
    (h1, u1), _, f = two_members(client)
    r = client.delete(f"/api/families/{f}/members/{u1['id']}", headers=h1)
    assert r.status_code == 400 and "владельца" in r.json()["detail"]


def test_last_member_leaving_deletes_family(client, owner):
    h, u, f = owner
    code = invite_code(client, h, f)
    client.post(f"/api/families/{f}/medicines", headers=h, json={"name": "Нурофен", "packages": [{"quantity": 1}]})
    assert client.delete(f"/api/families/{f}/members/{u['id']}", headers=h).status_code == 204
    assert client.get(f"/api/invites/{code}").status_code == 404
    assert client.get(f"/api/families/{f}", headers=h).status_code == 404


def test_remove_unknown_member(client, owner):
    h, _, f = owner
    assert client.delete(f"/api/families/{f}/members/99999", headers=h).status_code == 404


def test_join_by_code(client, owner):
    h1, _, f = owner
    code = invite_code(client, h1, f)
    h2, _ = register(client, "mom@example.com", "Мама")
    fam = client.post("/api/families/join", headers=h2, json={"code": code.lower()}).json()
    assert fam["id"] == f and fam["role"] == "member"
    # повторное вступление ничего не ломает и не понижает роль владельца
    assert client.post("/api/families/join", headers=h2, json={"code": code}).json()["role"] == "member"
    assert client.post("/api/families/join", headers=h1, json={"code": code}).json()["role"] == "owner"
    assert len(client.get(f"/api/families/{f}", headers=h1).json()["members"]) == 2
    assert client.post("/api/families/join", headers=h2, json={"code": "WRONG123"}).status_code == 404


def enable_billing(client, h, on=True):
    assert client.put("/api/admin/billing", headers=h, json={"enabled": on}).status_code == 200


def test_free_plan_allows_one_own_cabinet(client, owner):
    h, _, first = owner
    assert client.get("/api/auth/me", headers=h).json()["own_families_left"] is None  # платная версия выключена
    enable_billing(client, h)
    assert client.get("/api/auth/me", headers=h).json()["own_families_left"] == 0
    r = client.post("/api/families", headers=h, json={"name": "Дача"})
    assert r.status_code == 402 and r.headers["X-Plus-Feature"] == "cabinets"
    assert "одну свою аптечку" in r.json()["detail"]
    assert len(client.get("/api/auth/me", headers=h).json()["families"]) == 1


def test_plus_in_own_family_unlocks_more_cabinets(client, owner):
    h, _, first = owner
    enable_billing(client, h)
    assert client.put(f"/api/admin/families/{first}/plan", headers=h, json={"plan": "plus", "plus_until": None}).status_code == 200
    assert client.get("/api/auth/me", headers=h).json()["own_families_left"] is None
    assert client.post("/api/families", headers=h, json={"name": "Дача"}).status_code == 201
    assert client.post("/api/families", headers=h, json={"name": "Машина"}).status_code == 201


def test_cabinets_over_limit_are_kept_and_joining_is_free(client):
    (h1, _), (h2, u2), f = two_members(client)
    # Мама уже завела свою аптечку, пока платная версия была выключена.
    mine = client.post("/api/families", headers=h2, json={"name": "Бабушка"}).json()["id"]
    enable_billing(client, h1)  # первый аккаунт — администратор
    assert client.post("/api/families", headers=h2, json={"name": "Ещё одна"}).status_code == 402
    # Созданное раньше остаётся, и в неё можно зайти.
    assert client.get(f"/api/families/{mine}", headers=h2).status_code == 200
    # Вступить в чужую аптечку по приглашению можно и без Плюса.
    other = client.post("/api/families/join", headers=h1, json={"code": invite_code(client, h2, mine)})
    assert other.status_code == 200
    # Первую аптечку всегда можно создать: например, после выхода из всех семей.
    h3, _ = register(client, "dad@example.com", "Папа", invite=invite_code(client, h1, f))
    assert client.get("/api/auth/me", headers=h3).json()["own_families_left"] == 1
    assert client.post("/api/families", headers=h3, json={"name": "Гараж"}).status_code == 201

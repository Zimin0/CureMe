"""Проверка данных перед миграцией на «семья + аптечки»: находит группы, которые нельзя склеить без потери приватности."""
from tests.conftest import fid, register


def check(client, h):
    r = client.get("/api/admin/household-check", headers=h)
    assert r.status_code == 200
    return r.json()


def test_each_separate_family_is_its_own_household(client):
    admin, a = register(client)
    register(client, "masha@example.com", "Маша")
    rep = check(client, admin)
    assert rep["users"] == 2 and rep["families"] == 2 and rep["would_create_households"] == 2
    assert rep["conflicts"] == [] and rep["safe"] is True


def test_family_with_all_its_people_is_one_complete_household(client):
    admin, a = register(client)
    code = next(f for f in client.get("/api/admin/families", headers=admin).json() if f["id"] == fid(a))["invite_code"]
    register(client, "masha@example.com", "Маша", invite=code)
    rep = check(client, admin)
    assert rep["would_create_households"] == 1 and rep["households"][0]["complete"] is True
    assert rep["conflicts"] == [] and rep["safe"] is True


def test_person_in_two_families_with_different_people_is_a_conflict(client):
    admin, a = register(client)
    code = next(f for f in client.get("/api/admin/families", headers=admin).json() if f["id"] == fid(a))["invite_code"]
    register(client, "masha@example.com", "Маша", invite=code)
    # у владельца вторая аптечка, в которой Маши нет: склеить в одну семью нельзя без лишнего доступа
    assert client.post("/api/families", headers=admin, json={"name": "Дача"}).status_code == 201
    rep = check(client, admin)
    assert rep["safe"] is False and len(rep["conflicts"]) == 1
    assert any("masha@example.com не состоит в «Дача»" in m for m in rep["conflicts"][0]["missing"])


def test_several_own_families_of_one_person_are_not_a_conflict(client):
    admin, a = register(client)
    assert client.post("/api/families", headers=admin, json={"name": "С собой"}).status_code == 201
    rep = check(client, admin)
    assert rep["would_create_households"] == 1 and rep["safe"] is True


def test_multiple_owners_are_reported_but_safe(client):
    admin, a = register(client)
    code = next(f for f in client.get("/api/admin/families", headers=admin).json() if f["id"] == fid(a))["invite_code"]
    _, b = register(client, "masha@example.com", "Маша", invite=code)
    r = client.patch(f"/api/admin/families/{fid(a)}/members/{b['id']}", headers=admin, json={"role": "owner"})
    assert r.status_code == 200
    rep = check(client, admin)
    assert len(rep["multi_owner_families"]) == 1 and rep["safe"] is True


def test_free_family_above_new_limit_is_reported(client):
    admin, a = register(client)
    code = next(f for f in client.get("/api/admin/families", headers=admin).json() if f["id"] == fid(a))["invite_code"]
    for i in range(3):
        register(client, f"user{i}@example.com", f"Человек {i}", invite=code)
    rep = check(client, admin)
    assert rep["safe"] is True and len(rep["over_free_limits"]) == 1


def test_user_without_family_is_listed(client):
    admin, a = register(client)
    _, b = register(client, "masha@example.com", "Маша")
    assert client.delete(f"/api/admin/families/{fid(b)}", headers=admin).status_code == 204
    rep = check(client, admin)
    assert rep["users_without_family"] == ["masha@example.com"]


def test_report_is_admin_only(client):
    admin, _ = register(client)
    user, _ = register(client, "masha@example.com", "Маша")
    assert client.get("/api/admin/household-check", headers=user).status_code == 403

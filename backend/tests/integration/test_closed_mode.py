"""Закрытый режим: сайтом пользуются только администраторы и отмеченные ими аккаунты."""

from tests.conftest import fid, register


def close_site(client, admin_h, user_ids=()):
    r = client.put("/api/admin/access", json={"closed": True, "user_ids": list(user_ids)}, headers=admin_h)
    assert r.status_code == 200, r.text
    return r.json()


def test_site_is_open_by_default(client):
    assert client.get("/api/auth/access").json() == {"closed": False, "telegram": False, "debug": False}
    h, _ = register(client)
    assert client.get("/api/admin/access", headers=h).json() == {"closed": False, "user_ids": []}


def test_closed_mode_blocks_others_but_keeps_their_rights(client):
    admin_h, admin = register(client)                         # первый аккаунт — администратор
    tester_h, tester = register(client, "tester@example.com", "Тестер")
    other_h, other = register(client, "other@example.com", "Чужой")
    assert close_site(client, admin_h, [tester["id"], 999]) == {"closed": True, "user_ids": [tester["id"]]}

    assert client.get("/api/auth/access").json() == {"closed": True, "telegram": False, "debug": False}
    # администратор и тестировщик работают как раньше
    assert client.get(f"/api/families/{fid(admin)}/medicines", headers=admin_h).status_code == 200
    assert client.get(f"/api/families/{fid(tester)}/medicines", headers=tester_h).status_code == 200
    assert client.get("/api/auth/me", headers=tester_h).json()["access_blocked"] is False

    # остальные видят только свой профиль: аптечка закрыта
    me = client.get("/api/auth/me", headers=other_h).json()
    assert me["access_blocked"] is True
    assert client.get(f"/api/families/{fid(other)}/medicines", headers=other_h).status_code == 403
    assert client.get("/api/admin/access", headers=other_h).status_code == 403

    # но вход, согласие и удаление аккаунта работают — это права по 152-ФЗ
    login = client.post("/api/auth/login", json={"email": "other@example.com", "password": "secret123"})
    assert login.status_code == 200 and login.json()["user"]["access_blocked"] is True
    assert client.post("/api/auth/consent", json={"consent": True}, headers=other_h).status_code == 200
    assert client.request("DELETE", "/api/auth/me", json={"password": "secret123"}, headers=other_h).status_code == 204


def test_closed_mode_stops_registration(client):
    admin_h, _ = register(client)
    close_site(client, admin_h)
    r = client.post("/api/auth/register", json={"email": "new@example.com", "name": "Н", "password": "secret123", "consent": True})
    assert r.status_code == 403
    assert client.post("/api/auth/login", json={"email": "new@example.com", "password": "secret123"}).status_code == 401


def test_reopening_restores_access(client):
    admin_h, _ = register(client)
    other_h, other = register(client, "other@example.com", "Чужой")
    close_site(client, admin_h)
    assert client.get(f"/api/families/{fid(other)}/medicines", headers=other_h).status_code == 403
    client.put("/api/admin/access", json={"closed": False, "user_ids": []}, headers=admin_h)
    assert client.get(f"/api/families/{fid(other)}/medicines", headers=other_h).status_code == 200


def test_debug_mode_is_admin_switch_visible_to_everyone(client):
    admin_h, _ = register(client)
    user_h, _ = register(client, "user@example.com", "Обычный")
    assert client.get("/api/auth/access").json()["debug"] is False
    assert client.put("/api/admin/debug", json={"enabled": True}, headers=user_h).status_code == 403
    assert client.get("/api/auth/access").json()["debug"] is False
    assert client.put("/api/admin/debug", json={"enabled": True}, headers=admin_h).json() == {"enabled": True}
    assert client.get("/api/admin/debug", headers=admin_h).json() == {"enabled": True}
    assert client.get("/api/auth/access").json()["debug"] is True
    client.put("/api/admin/debug", json={"enabled": False}, headers=admin_h)
    assert client.get("/api/auth/access").json()["debug"] is False

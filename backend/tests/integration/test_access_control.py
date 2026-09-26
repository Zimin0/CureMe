"""Матрица доступа: кто какие эндпоинты может вызывать.

Один параметризованный тест прогоняет все защищённые маршруты — так новый
эндпоинт без проверки прав сразу будет заметен (достаточно добавить его в список).
"""

import pytest

from tests.conftest import fid, register

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 32

# (метод, путь, тело). {f} — семья, {m} — лекарство, {p} — упаковка, {c} — категория, {u} — участник.
FAMILY_ENDPOINTS = [
    ("GET", "/api/families/{f}", None),
    ("PATCH", "/api/families/{f}", {"name": "X"}),
    ("POST", "/api/families/{f}/invite", None),
    ("POST", "/api/families/{f}/members", {"email": "x@example.com"}),
    ("PATCH", "/api/families/{f}/members/{u}", {"role": "owner"}),
    ("DELETE", "/api/families/{f}/members/{u}", None),
    ("GET", "/api/families/{f}/categories", None),
    ("POST", "/api/families/{f}/categories", {"name": "X"}),
    ("PUT", "/api/families/{f}/categories/{c}", {"name": "X"}),
    ("DELETE", "/api/families/{f}/categories/{c}", None),
    ("GET", "/api/families/{f}/medicines", None),
    ("POST", "/api/families/{f}/medicines", {"name": "X"}),
    ("GET", "/api/families/{f}/medicines/{m}", None),
    ("PATCH", "/api/families/{f}/medicines/{m}", {"name": "X"}),
    ("DELETE", "/api/families/{f}/medicines/{m}", None),
    ("PUT", "/api/families/{f}/medicines/{m}/mark", {"is_favorite": True}),
    ("POST", "/api/families/{f}/medicines/{m}/consume", {"amount": 1}),
    ("POST", "/api/families/{f}/medicines/{m}/packages", {"quantity": 1}),
    ("PATCH", "/api/families/{f}/medicines/{m}/packages/{p}", {"quantity": 1}),
    ("DELETE", "/api/families/{f}/medicines/{m}/packages/{p}", None),
    ("PUT", "/api/families/{f}/medicines/{m}/photo", "photo"),
    ("DELETE", "/api/families/{f}/medicines/{m}/photo", None),
    ("GET", "/api/families/{f}/overview", None),
    ("GET", "/api/families/{f}/suggest?condition=боль", None),
    ("POST", "/api/families/{f}/scan", {"raw": "4601669002013"}),
    ("GET", "/api/families/{f}/export.txt", None),
]
IDS = [f"{m} {p}" for m, p, _ in FAMILY_ENDPOINTS]


@pytest.fixture
def world(client):
    """Семья Никиты (владелец + участник) и посторонний человек со своей семьёй."""
    h_owner, owner = register(client)
    f = fid(owner)
    code = client.get(f"/api/families/{f}", headers=h_owner).json()["invite_code"]
    h_member, member = register(client, "mom@example.com", "Мама", invite=code)
    h_stranger, stranger = register(client, "stranger@example.com", "Чужой")
    med = client.post(f"/api/families/{f}/medicines", headers=h_owner,
                      json={"name": "Нурофен", "packages": [{"quantity": 5}]}).json()
    ids = {
        "f": f, "m": med["id"], "p": med["packages"][0]["id"], "u": member["id"],
        "c": client.get(f"/api/families/{f}/categories", headers=h_owner).json()[0]["id"],
    }
    return {"owner": h_owner, "member": h_member, "stranger": h_stranger, "stranger_family": fid(stranger), "ids": ids}


def call(client, method, path, body, headers, ids):
    url = path.format(**ids)
    if body == "photo":
        return client.request(method, url, headers=headers, files={"file": ("p.jpg", JPEG, "image/jpeg")})
    return client.request(method, url, headers=headers, json=body)


@pytest.mark.parametrize("method, path, body", FAMILY_ENDPOINTS, ids=IDS)
def test_anonymous_gets_401(client, world, method, path, body):
    assert call(client, method, path, body, {}, world["ids"]).status_code == 401


@pytest.mark.parametrize("method, path, body", FAMILY_ENDPOINTS, ids=IDS)
def test_stranger_gets_404(client, world, method, path, body):
    """Чужой видит 404, а не 403: так нельзя даже узнать, что такая семья существует."""
    assert call(client, method, path, body, world["stranger"], world["ids"]).status_code == 404


OWNER_ONLY = {"PATCH /api/families/{f}", "POST /api/families/{f}/invite", "POST /api/families/{f}/members",
              "PATCH /api/families/{f}/members/{u}"}


@pytest.mark.parametrize("method, path, body", FAMILY_ENDPOINTS, ids=IDS)
def test_member_rights(client, world, method, path, body):
    r = call(client, method, path, body, world["member"], world["ids"])
    if f"{method} {path}" in OWNER_ONLY:
        assert r.status_code == 403
    else:
        assert r.status_code < 400, r.text  # участник ведёт общую аптечку наравне с владельцем


@pytest.mark.parametrize("method, path, body", [e for e in FAMILY_ENDPOINTS if "{m}" in e[1] or "{c}" in e[1]],
                         ids=[i for i, e in zip(IDS, FAMILY_ENDPOINTS) if "{m}" in e[1] or "{c}" in e[1]])
def test_foreign_objects_via_own_family(client, world, method, path, body):
    """Подставить id чужого лекарства в адрес своей семьи тоже не выйдет."""
    ids = {**world["ids"], "f": world["stranger_family"]}
    assert call(client, method, path, body, world["stranger"], ids).status_code == 404


def test_account_endpoints_require_login(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.patch("/api/auth/me", json={"name": "X"}).status_code == 401
    assert client.post("/api/families", json={"name": "X"}).status_code == 401
    assert client.post("/api/families/join", json={"code": "X"}).status_code == 401

"""Лимиты бесплатной версии: до 4 участников и 60 лекарств, в Плюсе без ограничений."""

import pytest

from app.models import Medicine
from app.plans import FREE_LIMITS, PLUS_HEADER
from tests.conftest import register

FREE_MAX_MEMBERS = FREE_LIMITS["members"]
FREE_MAX_MEDICINES = FREE_LIMITS["medicines"]


@pytest.fixture
def owner(client):
    """Владелец семьи; он же первый аккаунт, то есть администратор, и включает платную версию."""
    h, u = register(client)
    assert client.put("/api/admin/billing", headers=h, json={"enabled": True}).status_code == 200
    return h, u, u["families"][0]["id"]


def invite_code(client, h, f):
    return client.get(f"/api/families/{f}", headers=h).json()["invite_code"]


def usage(client, h, f):
    p = client.get(f"/api/families/{f}/plan", headers=h).json()
    return {"members": p["usage"]["members"], "max_members": p["limits"]["members"],
            "medicines": p["usage"]["medicines"], "max_medicines": p["limits"]["medicines"]}


def fill_medicines(db, f, n):
    """Быстро кладём лекарства прямо в базу: 60 запросов через API тесту не нужны."""
    db.add_all(Medicine(family_id=f, name=f"Лекарство {i}") for i in range(n))
    db.commit()


def fill_members(client, h, f, total):
    code = invite_code(client, h, f)
    for i in range(total - 1):
        register(client, f"member{i}@example.com", f"Участник {i}", invite=code)


def add(client, h, f, name="Нурофен"):
    return client.post(f"/api/families/{f}/medicines", headers=h, json={"name": name})


@pytest.fixture
def plus(client, owner):
    h, _, f = owner
    assert client.put(f"/api/admin/families/{f}/plan", headers=h, json={"plan": "plus", "plus_until": None}).status_code == 200


def test_usage_is_shown_in_family(client, owner):
    h, _, f = owner
    add(client, h, f)
    assert usage(client, h, f) == {
        "members": 1, "max_members": FREE_MAX_MEMBERS, "medicines": 1, "max_medicines": FREE_MAX_MEDICINES,
    }


def test_medicine_limit_blocks_only_adding(client, db, owner):
    h, _, f = owner
    fill_medicines(db, f, FREE_MAX_MEDICINES - 1)
    assert add(client, h, f, "Шестидесятое").status_code == 201
    assert usage(client, h, f)["medicines"] == FREE_MAX_MEDICINES

    r = add(client, h, f, "Лишнее")
    assert r.status_code == 402 and "60 лекарств" in r.json()["detail"]
    assert r.headers[PLUS_HEADER] == "no_limits"  # фронтенд откроет шторку «Без лимитов»
    # Скан добавляет лекарство тем же запросом, поэтому и он упирается в лимит.
    r = client.post(f"/api/families/{f}/medicines", headers=h, json={"name": "Со скана", "gtin": "4601669002013"})
    assert r.status_code == 402

    # Существующим лекарствам лимит не мешает: упаковки, правка и приём работают.
    med = client.get(f"/api/families/{f}/medicines", headers=h).json()[0]
    assert client.post(f"/api/families/{f}/medicines/{med['id']}/packages", headers=h, json={"quantity": 5}).status_code == 201
    assert client.patch(f"/api/families/{f}/medicines/{med['id']}", headers=h, json={"notes": "ok"}).status_code == 200

    # Удалил одно — место освободилось.
    assert client.delete(f"/api/families/{f}/medicines/{med['id']}", headers=h).status_code == 204
    assert add(client, h, f, "Вместо удалённого").status_code == 201


def test_medicines_with_zero_stock_count(client, owner):
    h, _, f = owner
    add(client, h, f, "Без упаковок")  # остаток 0, но лекарство в списке
    assert usage(client, h, f)["medicines"] == 1


def test_family_over_limit_keeps_its_data(client, db, owner):
    """Семья набрала больше до появления лимитов: всё видно, добавлять новое нельзя."""
    h, _, f = owner
    fill_medicines(db, f, FREE_MAX_MEDICINES + 15)
    assert len(client.get(f"/api/families/{f}/medicines", headers=h).json()) == FREE_MAX_MEDICINES + 15
    assert usage(client, h, f)["medicines"] == FREE_MAX_MEDICINES + 15
    assert add(client, h, f).status_code == 402


def test_limit_is_per_family(client, db, owner):
    h, _, f = owner
    fill_medicines(db, f, FREE_MAX_MEDICINES)
    # Вторая своя аптечка в бесплатной версии закрыта (test_families.py), поэтому
    # аптечку на даче заводит бабушка и зовёт в неё владельца.
    hg, g = register(client, "granny@example.com", "Бабушка")
    dacha = g["families"][0]["id"]
    assert client.post("/api/families/join", headers=h, json={"code": invite_code(client, hg, dacha)}).status_code == 200
    assert add(client, h, dacha).status_code == 201


def test_member_limit_on_join_by_link(client, owner):
    h, _, f = owner
    fill_members(client, h, f, FREE_MAX_MEMBERS)
    code = invite_code(client, h, f)
    assert client.get(f"/api/invites/{code}").json()["full"] is True

    # Уже зарегистрированный человек переходит по ссылке.
    h5, _ = register(client, "fifth@example.com", "Пятый")
    r = client.post("/api/families/join", headers=h5, json={"code": code})
    assert r.status_code == 402 and "владельца" in r.json()["detail"]
    assert usage(client, h, f)["members"] == FREE_MAX_MEMBERS

    # Тот, кто уже в семье, по ссылке заходит как раньше.
    assert client.post("/api/families/join", headers=h, json={"code": code}).status_code == 200


def test_member_limit_on_register_with_invite(client, owner):
    h, _, f = owner
    fill_members(client, h, f, FREE_MAX_MEMBERS)
    r = client.post("/api/auth/register", json={
        "email": "late@example.com", "name": "Опоздал", "password": "secret123",
        "invite_code": invite_code(client, h, f), "consent": True,
    })
    assert r.status_code == 402
    # Аккаунт не создан: человек может зарегистрироваться позже, когда место появится.
    assert client.post("/api/auth/login", json={"email": "late@example.com", "password": "secret123"}).status_code == 401


def test_member_limit_on_add_by_email(client, owner):
    h, _, f = owner
    fill_members(client, h, f, FREE_MAX_MEMBERS)
    register(client, "fifth@example.com", "Пятый")
    r = client.post(f"/api/families/{f}/members", headers=h, json={"email": "fifth@example.com"})
    assert r.status_code == 402 and "4 участника" in r.json()["detail"]

    # Кто-то вышел — место освободилось.
    uid = client.get(f"/api/families/{f}", headers=h).json()["members"][-1]["user_id"]
    assert client.delete(f"/api/families/{f}/members/{uid}", headers=h).status_code == 204
    assert client.post(f"/api/families/{f}/members", headers=h, json={"email": "fifth@example.com"}).status_code == 200


def test_admin_is_not_limited(client, owner):
    """Администратор сервиса может добавить участника сверх лимита (например, по просьбе семьи)."""
    h, _, f = owner  # первый аккаунт — администратор
    fill_members(client, h, f, FREE_MAX_MEMBERS)
    register(client, "fifth@example.com", "Пятый")
    r = client.post(f"/api/admin/families/{f}/members", headers=h, json={"email": "fifth@example.com"})
    assert r.status_code == 200
    assert usage(client, h, f)["members"] == FREE_MAX_MEMBERS + 1


def test_plus_has_no_limits(client, db, owner, plus):
    h, _, f = owner
    fill_medicines(db, f, FREE_MAX_MEDICINES)
    assert add(client, h, f).status_code == 201
    fill_members(client, h, f, FREE_MAX_MEMBERS + 1)
    assert usage(client, h, f) == {
        "members": FREE_MAX_MEMBERS + 1, "max_members": None, "medicines": FREE_MAX_MEDICINES + 1, "max_medicines": None,
    }
    assert client.get(f"/api/invites/{invite_code(client, h, f)}").json()["full"] is False


def test_no_limits_while_billing_is_off(client, db):
    """Пока платная версия выключена, лимитов нет ни у кого."""
    h, u = register(client)
    f = u["families"][0]["id"]
    fill_medicines(db, f, FREE_MAX_MEDICINES)
    assert add(client, h, f).status_code == 201
    fill_members(client, h, f, FREE_MAX_MEMBERS + 1)

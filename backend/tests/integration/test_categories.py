"""Категории: общий список для всех семей, менять его может только администратор.

Изменение категорий через админку проверяется в test_admin.py, здесь — то, что видит семья.
"""

import pytest

from tests.conftest import fid, register


def test_all_families_see_the_same_default_list(client, owner):
    h1, _, f1 = owner
    h2, u2 = register(client, "other@example.com", "Сосед")
    a = client.get(f"/api/families/{f1}/categories", headers=h1).json()
    b = client.get(f"/api/families/{fid(u2)}/categories", headers=h2).json()
    assert [c["id"] for c in a] == [c["id"] for c in b]
    assert [c["name"] for c in a][:2] == ["Обезболивающие", "Жаропонижающие"]
    assert len(a) == 12  # вторая регистрация не задвоила список


def test_medicine_count_is_per_family(client, owner):
    h1, _, f1 = owner
    h2, u2 = register(client, "other@example.com", "Сосед")
    cid = client.get(f"/api/families/{f1}/categories", headers=h1).json()[0]["id"]
    client.post(f"/api/families/{f1}/medicines", headers=h1, json={"name": "Нурофен", "category_id": cid})
    client.post(f"/api/families/{f1}/medicines", headers=h1, json={"name": "Кетанов", "category_id": cid})
    count = lambda h, f: next(c["medicine_count"] for c in client.get(f"/api/families/{f}/categories", headers=h).json() if c["id"] == cid)  # noqa: E731
    assert count(h1, f1) == 2 and count(h2, fid(u2)) == 0


@pytest.mark.parametrize("method, path", [
    ("POST", "/api/families/{f}/categories"),
    ("PUT", "/api/families/{f}/categories/1"),
    ("DELETE", "/api/families/{f}/categories/1"),
])
def test_family_cannot_change_categories(client, owner, method, path):
    """Таких маршрутов у семьи больше нет: 405 (метод не разрешён) или 404 (адреса нет)."""
    h, _, f = owner
    assert client.request(method, path.format(f=f), headers=h, json={"name": "Для кота"}).status_code in (404, 405)


def test_any_existing_category_can_be_assigned(client, owner):
    h, _, f = owner
    cats = client.get(f"/api/families/{f}/categories", headers=h).json()
    url = f"/api/families/{f}/medicines"
    m = client.post(url, headers=h, json={"name": "Тауфон", "category_id": cats[-1]["id"]}).json()
    assert m["category"]["name"] == cats[-1]["name"]
    assert client.post(url, headers=h, json={"name": "X", "category_id": 999999}).status_code == 400

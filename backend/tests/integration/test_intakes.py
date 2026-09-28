"""История приёма: запись при «Принял», объединение нажатий за минуту, комментарии."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import Intake
from tests.conftest import register


@pytest.fixture
def med(client, owner):
    h, _, f = owner
    m = client.post(f"/api/families/{f}/medicines", headers=h,
                    json={"name": "Нурофен", "unit": "таб", "packages": [{"quantity": 20}]}).json()
    return h, f, m["id"]


def take(client, h, f, mid, **body):
    r = client.post(f"/api/families/{f}/medicines/{mid}/consume", headers=h, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def history(client, h, f, **params):
    r = client.get(f"/api/families/{f}/intakes", headers=h, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def age(db, minutes: float):
    """Сдвигает все записи в прошлое, как будто нажимали minutes минут назад."""
    shift = timedelta(minutes=minutes)
    for i in db.scalars(select(Intake)):
        i.taken_at, i.last_at = i.taken_at - shift, i.last_at - shift
    db.commit()


def test_consume_writes_history(client, med):
    h, f, mid = med
    take(client, h, f, mid, amount=2)
    [i] = history(client, h, f)
    assert (i["medicine_id"], i["medicine_name"], i["unit"], i["amount"]) == (mid, "Нурофен", "таб", 2)
    assert (i["user_name"], i["mine"], i["comment"]) == ("Никита", True, "")
    assert datetime.fromisoformat(i["taken_at"]) > datetime.now(timezone.utc) - timedelta(minutes=1)


def test_presses_within_a_minute_are_merged(client, db, med):
    h, f, mid = med
    for _ in range(3):
        take(client, h, f, mid)
    [i] = history(client, h, f)
    assert i["amount"] == 3
    assert take(client, h, f, mid)["stock"]["total"] == 16  # остаток списывается за каждое нажатие


def test_window_counts_from_the_last_press(client, db, med):
    h, f, mid = med
    take(client, h, f, mid)
    age(db, 0.75)
    take(client, h, f, mid)          # через 45 с — та же запись
    age(db, 0.75)
    take(client, h, f, mid)          # ещё через 45 с после прошлого нажатия — всё ещё та же
    assert [i["amount"] for i in history(client, h, f)] == [3]
    age(db, 2)
    take(client, h, f, mid)          # через 2 минуты — новая запись
    assert [i["amount"] for i in history(client, h, f)] == [1, 3]


def test_not_merged_across_people_or_medicines(client, owner, med):
    h, f, mid = med
    code = client.get(f"/api/families/{f}", headers=h).json()["invite_code"]
    h_mom, _ = register(client, "mom@example.com", "Мама", invite=code)
    other = client.post(f"/api/families/{f}/medicines", headers=h,
                        json={"name": "Пенталгин", "packages": [{"quantity": 5}]}).json()["id"]
    take(client, h, f, mid)
    take(client, h_mom, f, mid)
    take(client, h, f, other)
    items = history(client, h, f)
    assert sorted((i["medicine_name"], i["user_name"]) for i in items) == [
        ("Нурофен", "Мама"), ("Нурофен", "Никита"), ("Пенталгин", "Никита")]
    assert len(history(client, h, f, medicine_id=mid)) == 2
    assert {i["user_name"] for i in history(client, h, f, mine=True)} == {"Никита"}


def test_comment_is_optional_and_joined_on_merge(client, med):
    h, f, mid = med
    take(client, h, f, mid, comment="  болит голова  ")
    take(client, h, f, mid)
    take(client, h, f, mid, comment="не прошло")
    [i] = history(client, h, f)
    assert (i["amount"], i["comment"]) == (3, "болит голова\nне прошло")
    r = client.post(f"/api/families/{f}/medicines/{mid}/consume", headers=h, json={"comment": "x" * 1001})
    assert r.status_code == 422


def test_comment_is_private_and_editable_by_author(client, owner, med):
    h, f, mid = med
    code = client.get(f"/api/families/{f}", headers=h).json()["invite_code"]
    h_mom, _ = register(client, "mom@example.com", "Мама", invite=code)
    take(client, h, f, mid, comment="после тренировки")
    [mine] = history(client, h, f)
    [seen_by_mom] = history(client, h_mom, f)
    assert (seen_by_mom["mine"], seen_by_mom["comment"], seen_by_mom["amount"]) == (False, "", 1)

    url = f"/api/families/{f}/intakes/{mine['id']}"
    assert client.patch(url, headers=h_mom, json={"comment": "чужое"}).status_code == 403
    r = client.patch(url, headers=h, json={"comment": "болела спина"})
    assert r.status_code == 200 and r.json()["comment"] == "болела спина"
    assert client.patch(f"/api/families/{f}/intakes/999999", headers=h, json={"comment": "x"}).status_code == 404


def test_history_survives_medicine_deletion(client, med):
    h, f, mid = med
    take(client, h, f, mid)
    assert client.delete(f"/api/families/{f}/medicines/{mid}", headers=h).status_code == 204
    [i] = history(client, h, f)
    assert (i["medicine_id"], i["medicine_name"]) == (None, "Нурофен")


def test_failed_consume_writes_nothing(client, owner):
    h, _, f = owner
    empty = client.post(f"/api/families/{f}/medicines", headers=h, json={"name": "Бинт"}).json()["id"]
    assert client.post(f"/api/families/{f}/medicines/{empty}/consume", headers=h, json={}).status_code == 400
    assert history(client, h, f) == []


def test_only_actually_taken_amount_is_recorded(client, owner):
    h, _, f = owner
    mid = client.post(f"/api/families/{f}/medicines", headers=h,
                      json={"name": "Смекта", "packages": [{"quantity": 2}]}).json()["id"]
    take(client, h, f, mid, amount=5)
    assert history(client, h, f)[0]["amount"] == 2


def test_paging_and_account_deletion(client, db, owner, med):
    h, f, mid = med
    code = client.get(f"/api/families/{f}", headers=h).json()["invite_code"]
    h_mom, _ = register(client, "mom@example.com", "Мама", invite=code)
    take(client, h, f, mid)
    age(db, 5)
    take(client, h_mom, f, mid)
    first = history(client, h, f, limit=1)
    assert [i["user_name"] for i in first] == ["Мама"]
    rest = history(client, h, f, before=first[0]["taken_at"])
    assert [i["user_name"] for i in rest] == ["Никита"]
    # удалил аккаунт — его история приёма удаляется вместе с ним
    r = client.request("DELETE", "/api/auth/me", headers=h_mom, json={"password": "secret123"})
    assert r.status_code == 204, r.text
    assert [i["user_name"] for i in history(client, h, f)] == ["Никита"]

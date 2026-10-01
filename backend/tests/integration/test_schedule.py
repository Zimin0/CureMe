"""Расписание приёма: назначения, серии приёмов, отметка «принят» по истории, права доступа."""

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import Intake, Schedule
from app.reminders import MSK
from app.schedule import is_active_on, occurrences
from tests.conftest import fid, register

MON = date(2026, 10, 5)  # понедельник


@pytest.fixture
def med(client, owner):
    h, u, f = owner
    m = client.post(f"/api/families/{f}/medicines", headers=h,
                    json={"name": "Амепрозол", "unit": "таб", "packages": [{"quantity": 30}]}).json()
    return h, u, f, m["id"]


def create(client, h, f, mid, **body):
    body = {"medicine_id": mid, "times": [480], "start_date": MON.isoformat(), **body}
    r = client.post(f"/api/families/{f}/schedule", headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_defaults_to_every_day(client, med):
    h, _, f, mid = med
    s = create(client, h, f, mid, times=[480, 1200])
    assert s["medicine_name"] == "Амепрозол" and s["unit"] == "таб"
    assert len(s["slots"]) == 14 and s["every_weeks"] == 1 and s["end_date"] is None
    assert client.get(f"/api/families/{f}/schedule", headers=h).json()[0]["id"] == s["id"]


def test_days_times_cross_product_and_dedup(client, med):
    h, _, f, mid = med
    s = create(client, h, f, mid, days=[1, 1, 3], times=[960, 480, 480])
    assert sorted((x["weekday"], x["minute"]) for x in s["slots"]) == [(1, 480), (1, 960), (3, 480), (3, 960)]


@pytest.mark.parametrize("body", [
    {"days": [7]}, {"days": []}, {"times": [1440]}, {"times": [-1]}, {"times": []}, {"amount": 0},
    {"every_weeks": 0}, {"end_date": "2026-10-01"},
])
def test_create_validation(client, med, body):
    h, _, f, mid = med
    r = client.post(f"/api/families/{f}/schedule", headers=h,
                    json={"medicine_id": mid, "times": [480], "start_date": MON.isoformat(), **body})
    assert r.status_code == 422


def test_remove_series_tuesday_1600(client, med):
    h, _, f, mid = med
    s = create(client, h, f, mid, days=[1, 2], times=[480, 960])
    url = f"/api/families/{f}/schedule/{s['id']}/remove"
    r = client.post(url, headers=h, json={"days": [1], "times": [960]})
    assert r.status_code == 200
    assert sorted((x["weekday"], x["minute"]) for x in r.json()["slots"]) == [(1, 480), (2, 480), (2, 960)]
    # «совсем не пью по средам»: только дни
    r = client.post(url, headers=h, json={"days": [2]})
    assert [(x["weekday"], x["minute"]) for x in r.json()["slots"]] == [(1, 480)]
    # «утренний приём вообще»: только время
    assert client.post(url, headers=h, json={"times": [480]}).status_code == 204
    assert client.get(f"/api/families/{f}/schedule", headers=h).json() == []


def test_remove_nothing_found_is_404(client, med):
    h, _, f, mid = med
    s = create(client, h, f, mid, days=[0])
    assert client.post(f"/api/families/{f}/schedule/{s['id']}/remove", headers=h, json={"days": [5]}).status_code == 404


def test_add_slots_and_move_slot(client, med):
    h, _, f, mid = med
    s = create(client, h, f, mid, days=[0], times=[480])
    base = f"/api/families/{f}/schedule/{s['id']}"
    s = client.post(f"{base}/slots", headers=h, json={"days": [0, 4], "times": [480, 1200]}).json()
    assert len(s["slots"]) == 4  # (0,480) уже был
    slot = next(x for x in s["slots"] if (x["weekday"], x["minute"]) == (4, 1200))
    moved = client.patch(f"{base}/slots/{slot['id']}", headers=h, json={"weekday": 5}).json()
    assert (5, 1200) in [(x["weekday"], x["minute"]) for x in moved["slots"]]
    clash = client.patch(f"{base}/slots/{slot['id']}", headers=h, json={"weekday": 0, "minute": 480})
    assert clash.status_code == 409


def test_update_and_delete(client, med):
    h, _, f, mid = med
    s = create(client, h, f, mid, end_date="2026-12-31")
    base = f"/api/families/{f}/schedule/{s['id']}"
    r = client.patch(base, headers=h, json={"amount": 2, "end_date": None, "every_weeks": 2}).json()
    assert r["amount"] == 2 and r["end_date"] is None and r["every_weeks"] == 2
    assert client.patch(base, headers=h, json={"end_date": "2026-01-01"}).status_code == 400
    assert client.delete(base, headers=h).status_code == 204
    assert client.delete(base, headers=h).status_code == 404


def test_schedule_is_private_to_its_owner(client, med):
    h, _, f, mid = med
    s = create(client, h, f, mid)
    inv = client.get(f"/api/families/{f}", headers=h).json()
    h2, _ = register(client, "mama@example.com", "Мама", invite=inv["invite_code"])
    assert client.get(f"/api/families/{f}/schedule", headers=h2).json() == []
    base = f"/api/families/{f}/schedule/{s['id']}"
    assert client.delete(base, headers=h2).status_code == 404
    assert client.post(f"{base}/remove", headers=h2, json={}).status_code == 404
    # и чужое лекарство в назначение не положить
    other = register(client, "x@example.com", "Чужой")
    r = client.post(f"/api/families/{fid(other[1])}/schedule", headers=other[0],
                    json={"medicine_id": mid, "times": [480]})
    assert r.status_code == 404


def test_leaving_family_drops_schedule(client, med, db):
    h, _, f, mid = med
    inv = client.get(f"/api/families/{f}", headers=h).json()
    h2, u2 = register(client, "mama@example.com", "Мама", invite=inv["invite_code"])
    client.post(f"/api/families/{f}/schedule", headers=h2, json={"medicine_id": mid, "times": [480]})
    assert db.scalar(select(Schedule.id).where(Schedule.user_id == u2["id"])) is not None
    assert client.delete(f"/api/families/{f}/members/{u2['id']}", headers=h2).status_code == 204
    db.expire_all()
    assert db.scalar(select(Schedule.id).where(Schedule.user_id == u2["id"])) is None


def test_deleting_medicine_keeps_name(client, med, db):
    h, _, f, mid = med
    create(client, h, f, mid)
    assert client.delete(f"/api/families/{f}/medicines/{mid}", headers=h).status_code == 204
    s = client.get(f"/api/families/{f}/schedule", headers=h).json()[0]
    assert s["medicine_id"] is None and s["medicine_name"] == "Амепрозол"


def test_active_days_and_every_other_week():
    s = Schedule(start_date=MON, end_date=MON + timedelta(days=20), every_weeks=2)
    assert is_active_on(s, MON) and is_active_on(s, MON + timedelta(days=6))
    assert not is_active_on(s, MON + timedelta(days=7)) and not is_active_on(s, MON + timedelta(days=13))
    assert is_active_on(s, MON + timedelta(days=14)) and not is_active_on(s, MON + timedelta(days=21))
    assert not is_active_on(s, MON - timedelta(days=1))


def _intake_at(db, user_id, medicine_id, local: datetime):
    db.add(Intake(family_id=1, medicine_id=medicine_id, medicine_name="Амепрозол", user_id=user_id, amount=1,
                  taken_at=local.astimezone(timezone.utc), last_at=local.astimezone(timezone.utc)))
    db.commit()


def test_occurrences_marked_taken_from_history(client, med, db):
    h, u, f, mid = med
    create(client, h, f, mid, days=[0], times=[480, 1200])  # пн 08:00 и 20:00
    at = lambda hh, mm: datetime(2026, 10, 5, hh, mm, tzinfo=MSK)  # noqa: E731
    _intake_at(db, u["id"], mid, at(8, 40))  # с опозданием — засчитано за утро
    r = client.get(f"/api/families/{f}/schedule/occurrences", headers=h, params={"since": "2026-10-05"}).json()
    assert [(o["minute"], o["taken"]) for o in r] == [(480, True), (1200, False)]
    assert r[0]["medicine_name"] == "Амепрозол" and r[0]["taken_at"]


def test_one_intake_closes_only_one_occurrence(client, med, db):
    h, u, f, mid = med
    create(client, h, f, mid, days=[0], times=[480, 510])  # 08:00 и 08:30
    _intake_at(db, u["id"], mid, datetime(2026, 10, 5, 8, 10, tzinfo=MSK))
    occ = occurrences(db, u["id"], MON, MON)
    assert [o.taken_at is not None for o in occ] == [True, False]


def test_someone_elses_intake_does_not_count(client, med, db):
    h, u, f, mid = med
    create(client, h, f, mid, days=[0])
    inv = client.get(f"/api/families/{f}", headers=h).json()
    _, u2 = register(client, "mama@example.com", "Мама", invite=inv["invite_code"])
    _intake_at(db, u2["id"], mid, datetime(2026, 10, 5, 8, 5, tzinfo=MSK))
    assert not occurrences(db, u["id"], MON, MON)[0].taken_at


def test_occurrences_range_limit(client, med):
    h, _, f, _ = med
    r = client.get(f"/api/families/{f}/schedule/occurrences", headers=h,
                   params={"since": "2026-10-01", "until": "2026-12-01"})
    assert r.status_code == 400


def test_create_needs_plus_but_existing_stays(client, med, db):
    from app.models import AppSetting
    h, _, f, mid = med
    s = create(client, h, f, mid)  # платная версия выключена: всем можно
    db.add(AppSetting(key="billing", value={"enabled": True}))
    db.commit()  # теперь у семьи free
    r = client.post(f"/api/families/{f}/schedule", headers=h, json={"medicine_id": mid, "times": [480]})
    assert r.status_code == 402 and r.headers["X-Plus-Feature"] == "schedule"
    assert client.get(f"/api/families/{f}/schedule", headers=h).json()[0]["id"] == s["id"]
    assert client.delete(f"/api/families/{f}/schedule/{s['id']}", headers=h).status_code == 204

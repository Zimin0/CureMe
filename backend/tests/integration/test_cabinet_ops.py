"""Перенос лекарств между аптечками, разделение, поиск по всем аптечкам, выгрузка (R17, R18, R05-T3/T4, R25, BC16, BC17)."""
import csv
import io
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from app.models import Family, Intake, Medicine, Schedule, User, UserMark
from tests.conftest import check_household_invariants, fid, grant_plus, register


def enable_billing(client, h):
    assert client.put("/api/admin/billing", headers=h, json={"enabled": True, "price_month": 199, "price_year": 1990, "trial_days": 0}).status_code == 200


def add_med(client, h, f, name, gtin=None, qty=10, **extra):
    body = {"name": name, "unit": "таб", "packages": [{"quantity": qty}], **extra}
    if gtin:
        body["gtin"] = gtin
    r = client.post(f"/api/families/{f}/medicines", headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def new_cabinet(client, h, name):
    r = client.post("/api/families", headers=h, json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def names(client, h, f):
    return sorted(m["name"] for m in client.get(f"/api/families/{f}/medicines", headers=h).json())


def freeze(session_factory, fam_id):
    with session_factory() as db:
        db.get(Family, fam_id).status = "frozen"
        db.commit()


@pytest.fixture
def plus_house(client):
    """Семья с Плюсом из владельца и двух аптечек: «Семья Никита» (A) и «Дача» (B)."""
    h, u = register(client)
    enable_billing(client, h)
    a = fid(u)
    grant_plus(client, h, a)
    b = new_cabinet(client, h, "Дача")
    return h, u, a, b


def test_r17_t1_move_selected_medicines(client, plus_house, session_factory):
    h, u, a, b = plus_house
    x, y = add_med(client, h, a, "Нурофен"), add_med(client, h, a, "Парацетамол")
    r = client.post(f"/api/families/{a}/medicines/move", headers=h, json={"to_family_id": b, "medicine_ids": [x["id"]]})
    assert r.status_code == 200 and r.json() == {"moved": 1, "merged": 0, "to_family_id": b}
    assert names(client, h, a) == ["Парацетамол"] and names(client, h, b) == ["Нурофен"]
    assert client.get(f"/api/families/{b}/medicines/{x['id']}", headers=h).json()["stock"]["total"] == 10  # упаковки с ним
    check_household_invariants(session_factory)


def test_r17_t1_any_member_may_move(client, plus_house):
    h, u, a, b = plus_house
    code = client.get(f"/api/families/{a}", headers=h).json()["invite_code"]
    hm, _ = register(client, "mom@example.com", "Мама", invite=code)
    m = add_med(client, hm, a, "Но-шпа")
    assert client.post(f"/api/families/{a}/medicines/move", headers=hm, json={"to_family_id": b, "medicine_ids": [m["id"]]}).status_code == 200


def test_r17_t2_bc16_duplicates_by_barcode_are_merged(client, plus_house, session_factory):
    """BC16: остатки сложены, история приёма, расписание и отметки живы и привязаны к оставшейся карточке."""
    h, u, a, b = plus_house
    gtin = "4601669002013"
    src = add_med(client, h, a, "Нурофен", gtin=gtin, qty=6)
    dst = add_med(client, h, b, "Нурофен в Даче", gtin=gtin, qty=4)
    assert client.post(f"/api/families/{a}/medicines/{src['id']}/consume", headers=h, json={"amount": 1}).status_code == 200
    assert client.put(f"/api/families/{a}/medicines/{src['id']}/mark", headers=h, json={"is_favorite": True, "helps_me": True, "personal_note": "ночью"}).status_code == 200
    with session_factory() as db:  # расписание на исходное лекарство
        db.add(Schedule(family_id=a, user_id=u["id"], medicine_id=src["id"], medicine_name="Нурофен", unit="таб", amount=1,
                        start_date=datetime.now(timezone.utc).date()))
        db.commit()
    r = client.post(f"/api/families/{a}/medicines/move", headers=h, json={"to_family_id": b, "medicine_ids": [src["id"]]})
    assert r.status_code == 200 and r.json()["merged"] == 1 and r.json()["moved"] == 1
    assert names(client, h, a) == [] and names(client, h, b) == ["Нурофен в Даче"]
    merged = client.get(f"/api/families/{b}/medicines/{dst['id']}", headers=h).json()
    assert merged["stock"]["total"] == 9 and len(merged["packages"]) == 2  # 5 + 4: остатки сложены
    assert merged["is_favorite"] and merged["helps_me"] and merged["personal_note"] == "ночью"
    with session_factory() as db:
        assert db.get(Medicine, src["id"]) is None
        intake = db.scalar(select(Intake))
        assert (intake.medicine_id, intake.family_id) == (dst["id"], b)
        sched = db.scalar(select(Schedule))
        assert (sched.medicine_id, sched.family_id) == (dst["id"], b)
    assert [i["medicine_name"] for i in client.get(f"/api/families/{b}/intakes", headers=h).json()] == ["Нурофен"]
    check_household_invariants(session_factory)


def test_r17_marks_of_both_cards_are_merged(client, plus_house, session_factory):
    h, u, a, b = plus_house
    gtin = "4601669002013"
    src, dst = add_med(client, h, a, "Н", gtin=gtin), add_med(client, h, b, "Н2", gtin=gtin)
    client.put(f"/api/families/{a}/medicines/{src['id']}/mark", headers=h, json={"helps_me": True})
    client.put(f"/api/families/{b}/medicines/{dst['id']}/mark", headers=h, json={"is_favorite": True})
    client.post(f"/api/families/{a}/medicines/move", headers=h, json={"to_family_id": b, "medicine_ids": [src["id"]]})
    with session_factory() as db:
        marks = db.scalars(select(UserMark)).all()
        assert len(marks) == 1 and marks[0].medicine_id == dst["id"] and marks[0].is_favorite and marks[0].helps_me


def test_r17_history_and_schedule_follow_a_moved_card(client, plus_house, session_factory):
    h, u, a, b = plus_house
    m = add_med(client, h, a, "Аспирин")
    client.post(f"/api/families/{a}/medicines/{m['id']}/consume", headers=h, json={"amount": 1})
    client.post(f"/api/families/{a}/medicines/move", headers=h, json={"to_family_id": b, "medicine_ids": [m["id"]]})
    assert client.get(f"/api/families/{a}/intakes", headers=h).json() == []
    assert [i["medicine_name"] for i in client.get(f"/api/families/{b}/intakes", headers=h).json()] == ["Аспирин"]


def test_r17_t3_foreign_cabinet_and_foreign_medicine_are_404(client, plus_house):
    h, u, a, b = plus_house
    hs, stranger = register(client, "stranger@example.com", "Чужой")
    m = add_med(client, h, a, "Нурофен")
    foreign = fid(stranger)
    assert client.post(f"/api/families/{a}/medicines/move", headers=h, json={"to_family_id": foreign, "medicine_ids": [m["id"]]}).status_code == 404
    assert client.post(f"/api/families/{a}/medicines/move", headers=h, json={"to_family_id": 99999, "medicine_ids": [m["id"]]}).status_code == 404
    assert client.post(f"/api/families/{a}/medicines/move", headers=hs, json={"to_family_id": b, "medicine_ids": [m["id"]]}).status_code == 404  # чужой по адресу
    assert client.post(f"/api/families/{a}/medicines/move", headers=h, json={"to_family_id": b, "medicine_ids": [m["id"], 99999]}).status_code == 404
    assert names(client, h, a) == ["Нурофен"]  # ничего не сдвинулось


def test_r17_same_cabinet_is_rejected(client, plus_house):
    h, u, a, b = plus_house
    m = add_med(client, h, a, "Нурофен")
    assert client.post(f"/api/families/{a}/medicines/move", headers=h, json={"to_family_id": a, "medicine_ids": [m["id"]]}).status_code == 422


def test_r17_t4_frozen_target_is_refused_but_frozen_source_may_be_emptied(client, plus_house, session_factory):
    h, u, a, b = plus_house
    m = add_med(client, h, b, "Нурофен")
    n = add_med(client, h, a, "Парацетамол")
    freeze(session_factory, a)
    r = client.post(f"/api/families/{b}/medicines/move", headers=h, json={"to_family_id": a, "medicine_ids": [m["id"]]})
    assert r.status_code == 409 and "замороженную" in r.json()["detail"]
    # из замороженной аптечки переносить можно: так владелец освобождает её
    r = client.post(f"/api/families/{a}/medicines/move", headers=h, json={"to_family_id": b, "medicine_ids": [n["id"]]})
    assert r.status_code == 200
    assert names(client, h, b) == ["Нурофен", "Парацетамол"]
    # а обычное изменение замороженной по-прежнему закрыто
    assert client.post(f"/api/families/{a}/medicines", headers=h, json={"name": "Новое"}).status_code == 409


def _fill(session_factory, family_id, count, owner_id, gtin_first=None):
    with session_factory() as db:
        for i in range(count):
            db.add(Medicine(family_id=family_id, name=f"Л{i:02d}", created_by_id=owner_id, gtin=gtin_first if i == 0 else None))
        db.commit()


def test_r17_t5_free_limit_of_60_is_not_exceeded(client, session_factory):
    """Приёмник бесплатной семьи на 60 карточках: новая карточка не помещается (402), слияние с имеющейся помещается."""
    h, u = register(client)
    enable_billing(client, h)
    a = fid(u)
    # у бесплатной семьи из одного человека одна аптечка: вторая нужна, значит человек второй
    code = client.get(f"/api/families/{a}", headers=h).json()["invite_code"]
    register(client, "mom@example.com", "Мама", invite=code)
    b = new_cabinet(client, h, "Дача")
    dup = add_med(client, h, a, "Дубль", gtin="4601669002013")
    _fill(session_factory, b, 60, u["id"], gtin_first=dup["gtin"])  # штрихкод хранится в нормальном виде, берём из карточки
    fresh = add_med(client, h, a, "Новое")
    r = client.post(f"/api/families/{a}/medicines/move", headers=h, json={"to_family_id": b, "medicine_ids": [fresh["id"]]})
    assert r.status_code == 402 and r.headers["X-Plus-Feature"] == "no_limits"
    assert names(client, h, a) == ["Дубль", "Новое"]
    r = client.post(f"/api/families/{a}/medicines/move", headers=h, json={"to_family_id": b, "medicine_ids": [dup["id"]]})
    assert r.status_code == 200 and r.json()["merged"] == 1  # слияние карточек не добавляет
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Medicine).where(Medicine.family_id == b)) == 60


def test_r18_t1_bc17_split_into_new_cabinet(client, plus_house, session_factory):
    h, u, a, b = plus_house
    x, y = add_med(client, h, a, "Нурофен"), add_med(client, h, a, "Парацетамол")
    client.post(f"/api/families/{a}/medicines/{x['id']}/consume", headers=h, json={"amount": 1})
    r = client.post(f"/api/families/{a}/split", headers=h, json={"name": "Машина", "medicine_ids": [x["id"]]})
    assert r.status_code == 201 and r.json()["moved"] == 1
    new = r.json()["to_family_id"]
    assert names(client, h, new) == ["Нурофен"] and names(client, h, a) == ["Парацетамол"]
    assert [c["name"] for c in client.get("/api/auth/me", headers=h).json()["families"]] == ["Семья Никита", "Дача", "Машина"]
    assert [i["medicine_name"] for i in client.get(f"/api/families/{new}/intakes", headers=h).json()] == ["Нурофен"]
    check_household_invariants(session_factory)


def test_r18_t2_no_free_slot_refuses_with_cabinets_feature_and_changes_nothing(client, session_factory):
    h, u = register(client)
    enable_billing(client, h)
    a = fid(u)
    m = add_med(client, h, a, "Нурофен")
    r = client.post(f"/api/families/{a}/split", headers=h, json={"name": "Дача", "medicine_ids": [m["id"]]})
    assert r.status_code == 402 and r.headers["X-Plus-Feature"] == "cabinets"
    assert names(client, h, a) == ["Нурофен"] and len(client.get("/api/auth/me", headers=h).json()["families"]) == 1


def test_r18_split_with_unknown_medicine_creates_no_cabinet(client, plus_house):
    h, u, a, b = plus_house
    r = client.post(f"/api/families/{a}/split", headers=h, json={"name": "Машина", "medicine_ids": [99999]})
    assert r.status_code == 404
    assert len(client.get("/api/auth/me", headers=h).json()["families"]) == 2


def test_r17_r18_endpoints_need_login_and_membership(client, plus_house):
    h, u, a, b = plus_house
    hs, _ = register(client, "stranger@example.com", "Чужой")
    body = {"to_family_id": b, "medicine_ids": [1]}
    assert client.post(f"/api/families/{a}/medicines/move", json=body).status_code == 401
    assert client.post(f"/api/families/{a}/split", json={"name": "X", "medicine_ids": [1]}).status_code == 401
    assert client.post(f"/api/families/{a}/split", headers=hs, json={"name": "X", "medicine_ids": [1]}).status_code == 404


# --- поиск и подбор по всем аптечкам (R05) ---
def test_r05_t3_free_family_searches_only_the_open_cabinet(client, session_factory):
    h, u = register(client)
    enable_billing(client, h)
    a = fid(u)
    code = client.get(f"/api/families/{a}", headers=h).json()["invite_code"]
    register(client, "mom@example.com", "Мама", invite=code)
    b = new_cabinet(client, h, "Дача")
    add_med(client, h, a, "Нурофен", indications="головная боль")
    add_med(client, h, b, "Нурофен Дача", indications="головная боль")
    assert names(client, h, a) == ["Нурофен"]  # обычный поиск: только открытая аптечка
    r = client.get(f"/api/families/{a}/medicines?scope=all&q=нурофен", headers=h)
    assert r.status_code == 402 and r.headers["X-Plus-Feature"] == "search_all"
    r = client.get(f"/api/families/{a}/suggest?condition=головная боль&scope=all", headers=h)
    assert r.status_code == 402 and r.headers["X-Plus-Feature"] == "search_all"
    ok = client.get(f"/api/families/{a}/suggest?condition=головная боль", headers=h).json()["results"]
    assert [x["medicine"]["name"] for x in ok] == ["Нурофен"]


def test_r05_t4_plus_searches_every_cabinet_of_the_family_and_nobody_elses(client, plus_house, session_factory):
    h, u, a, b = plus_house
    add_med(client, h, a, "Нурофен", indications="головная боль")
    add_med(client, h, b, "Нурофен Дача", indications="головная боль")
    frozen = new_cabinet(client, h, "Старая")
    add_med(client, h, frozen, "Нурофен Старый", indications="головная боль")
    hs, stranger = register(client, "stranger@example.com", "Чужой")
    add_med(client, hs, fid(stranger), "Нурофен Чужой", indications="головная боль")
    freeze(session_factory, frozen)
    rows = client.get(f"/api/families/{a}/medicines?scope=all&q=нурофен", headers=h).json()
    assert [(r["name"], r["family_name"]) for r in rows] == [("Нурофен", "Семья Никита"), ("Нурофен Дача", "Дача")]
    assert all(r["family_id"] in (a, b) for r in rows)
    got = client.get(f"/api/families/{b}/suggest?condition=головная боль&scope=all", headers=h).json()["results"]
    assert sorted(x["medicine"]["name"] for x in got) == ["Нурофен", "Нурофен Дача"]
    assert {x["medicine"]["family_name"] for x in got} == {"Семья Никита", "Дача"}
    plain = client.get(f"/api/families/{a}/medicines", headers=h).json()
    assert [r["family_id"] for r in plain] == [None]  # без scope лекарства без пометки аптечки


def test_r05_t5_with_billing_off_everything_is_open(client):
    h, u = register(client)
    a = fid(u)
    add_med(client, h, a, "Нурофен")
    assert client.get(f"/api/families/{a}/medicines?scope=all", headers=h).status_code == 200


def test_search_scope_rejects_other_values(client, plus_house):
    h, u, a, b = plus_house
    assert client.get(f"/api/families/{a}/medicines?scope=world", headers=h).status_code == 422


# --- выгрузка (R25) ---
def test_r25_t1_free_family_exports_json_and_csv(client, session_factory):
    h, u = register(client)
    enable_billing(client, h)
    a = fid(u)
    m = add_med(client, h, a, "Нурофен", dosage="200 мг", qty=7)
    client.post(f"/api/families/{a}/medicines/{m['id']}/consume", headers=h, json={"amount": 1, "comment": "голова"})
    j = client.get(f"/api/families/{a}/export.json", headers=h)
    assert j.status_code == 200 and "attachment" in j.headers["content-disposition"]
    data = json.loads(j.content)
    assert data["medicines"][0]["name"] == "Нурофен" and data["medicines"][0]["packages"][0]["quantity"] == 6
    assert [(i["medicine"], i["comment"]) for i in data["my_intakes"]] == [("Нурофен", "голова")]
    c = client.get(f"/api/families/{a}/export.csv", headers=h)
    assert c.status_code == 200 and c.content.startswith("﻿".encode())
    rows = list(csv.reader(io.StringIO(c.content.decode("utf-8-sig"))))
    assert rows[0][0] == "Лекарство" and rows[1][0] == "Нурофен" and rows[1][11] == "6.0"
    assert client.get(f"/api/families/{a}/export.xml", headers=h).status_code == 404


def test_r25_t2_frozen_cabinet_can_be_exported(client, plus_house, session_factory):
    h, u, a, b = plus_house
    add_med(client, h, b, "Нурофен")
    freeze(session_factory, b)
    assert client.get(f"/api/families/{b}/export.json", headers=h).status_code == 200
    assert client.get(f"/api/families/{b}/export.csv", headers=h).status_code == 200


def test_r25_t3_foreign_cabinet_cannot_be_exported(client, plus_house):
    h, u, a, b = plus_house
    hs, _ = register(client, "stranger@example.com", "Чужой")
    assert client.get(f"/api/families/{a}/export.json", headers=hs).status_code == 404
    assert client.get(f"/api/families/{a}/export.csv").status_code == 401

"""Окончание Плюса и сжатие семьи (R13, R14, R15, BC12–BC15): окно выбора, письма, выбор владельца, заморозка, возобновление."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app import compression
from app.models import Family, Household, HouseholdEvent, Medicine, User
from tests.conftest import check_household_invariants, fid, grant_plus, invite_of, register

DAY = timedelta(days=1)


@pytest.fixture
def letters(monkeypatch):
    """Письма, которые ушли бы людям: (кому, тема, текст)."""
    sent = []
    monkeypatch.setattr(compression, "send_mail", lambda to, subject, text, html=None: sent.append((to, subject, text)) or True)
    return sent


def me(client, h):
    return client.get("/api/auth/me", headers=h).json()


def run(session_factory, now):
    with session_factory() as db:
        return compression.run(db, now)


def cabinets(client, h):
    return {f["name"]: f for f in me(client, h)["families"]}


@pytest.fixture
def big(client, session_factory, letters):
    """BC12: семья из 5 человек и 8 аптечек с Плюсом, платная версия и сжатие включены.

    Люди вступили по очереди: владелец Никита, затем Вторая, Третий, Четвёртый, Пятая. Аптечки (по порядку создания):
    «Семья Никита» (владельца), «В1», «В2» (Вторая), «Т1» (Третий), «П1» (Пятая), «Н1», «Н2», «Н3» (владелец). В каждой по лекарству.
    """
    h, owner = register(client)
    assert client.put("/api/admin/billing", headers=h, json={"enabled": True, "price_month": 199, "price_year": 1990, "trial_days": 0}).status_code == 200
    assert client.put("/api/admin/compression", headers=h, json={"enabled": True}).status_code == 200
    f = fid(owner)
    grant_plus(client, h, f)
    people = {"owner": (h, owner)}
    for key, name in (("p2", "Вторая"), ("p3", "Третий"), ("p4", "Четвёртый"), ("p5", "Пятая")):
        hm, u = register(client, f"{key}@example.com", name, invite=invite_of(client, h, f))
        people[key] = (hm, u)
    for who, names in (("p2", ["В1", "В2"]), ("p3", ["Т1"]), ("p5", ["П1"]), ("owner", ["Н1", "Н2", "Н3"])):
        for name in names:
            assert client.post("/api/families", headers=people[who][0], json={"name": name}).status_code == 201
    for fam in me(client, h)["families"]:
        client.post(f"/api/families/{fam['id']}/medicines", headers=h,
                    json={"name": f"Лекарство {fam['name']}", "unit": "таб", "packages": [{"quantity": 30}]})
    assert len(me(client, h)["families"]) == 8
    with session_factory() as db:  # семья собрана до 13.10.2026 и получила «было четверо»; здесь проверяем общий случай (три человека)
        db.get(User, owner["id"]).household.kept_four = False
        db.commit()
    check_household_invariants(session_factory)
    return people


def plus_ends(session_factory, owner_id, until):
    with session_factory() as db:
        house = db.get(User, owner_id).household
        house.plan, house.plus_until, house.plus_is_trial = "plus", until, False
        db.commit()


T0_REAL = lambda: datetime.now(timezone.utc) - timedelta(hours=1)  # noqa: E731  Плюс кончился час назад


def household(session_factory, uid):
    with session_factory() as db:
        user = db.get(User, uid)
        return user.household_id


def test_r13_t1_paid_functions_close_for_everyone_at_once(client, big, session_factory):
    h, owner = big["owner"]
    plus_ends(session_factory, owner["id"], T0_REAL())
    for who in ("owner", "p5"):
        hh, u = big[who]
        plan = client.get(f"/api/families/{fid(owner)}/plan", headers=hh).json()
        assert plan["has_plus"] is False


def test_r13_t2_people_and_cabinets_stay_available_for_five_days(client, big, session_factory, letters):
    h, owner = big["owner"]
    t0 = T0_REAL()
    plus_ends(session_factory, owner["id"], t0)
    run(session_factory, t0 + 4 * DAY + timedelta(hours=1))  # четыре дня: письма, но никого не трогаем
    assert len(client.get(f"/api/families/{fid(owner)}", headers=h).json()["members"]) == 5
    assert {f["status"] for f in me(client, h)["families"]} == {"active"} and len(me(client, h)["families"]) == 8
    fam = me(client, h)["families"][0]
    meds = client.get(f"/api/families/{fam['id']}/medicines", headers=big["p5"][0]).json()  # любой человек всё ещё видит
    assert meds and client.post(f"/api/families/{fam['id']}/medicines/{meds[0]['id']}/consume", headers=big["p5"][0], json={}).status_code == 200
    # новых людей и аптечек сверх бесплатных лимитов нет
    assert client.post("/api/families", headers=h, json={"name": "Лишняя"}).status_code == 402
    check_household_invariants_allowing_overflow(session_factory)


def check_household_invariants_allowing_overflow(session_factory):
    """Пока идёт окно выбора, семья нарушает бесплатные лимиты, так и задумано: проверяем остальное."""
    from app.households import invariant_problems

    with session_factory() as db:
        problems = [p for p in invariant_problems(db) if not p.startswith(("R02: в семье", "R03:"))]
    assert problems == [], problems


def test_r13_t3_letters_and_banner_come_on_the_right_days_without_duplicates(client, big, session_factory, letters):
    h, owner = big["owner"]
    now = datetime.now(timezone.utc)
    until = now + timedelta(days=2, hours=12)  # осталось меньше трёх дней
    plus_ends(session_factory, owner["id"], until)
    # За 3 дня: письмо владельцу, баннер всем.
    banner = me(client, big["p4"][0])["plus_ending"]
    assert banner["state"] == "ending" and banner["is_owner"] is False
    assert me(client, h)["plus_ending"]["is_owner"] is True
    run(session_factory, now)
    run(session_factory, now + timedelta(hours=1))  # повторный проход письмо не дублирует
    assert [(to, "заканчивается" in subj) for to, subj, _ in letters] == [("nikita@example.com", True)]
    body = letters[0][2]
    assert "Ничего не удаляется" in body and "http" not in body and "до " in body
    # В день конца (часы теста: срок наступил час назад, письмо первой ступени уже было).
    t0 = T0_REAL()
    plus_ends(session_factory, owner["id"], t0)
    run(session_factory, t0 + timedelta(minutes=5))
    run(session_factory, t0 + timedelta(hours=3))
    assert [subj for _, subj, _ in letters][1:] == ["Капсулка: Плюс вашей семьи закончился"]
    assert "5 человек" in letters[1][2] and "3 человек" in letters[1][2] and "2 человек" in letters[1][2]  # было, лимит, уйдут
    assert me(client, big["p3"][0])["plus_ending"]["state"] == "ended"
    # Через 3 и 4 дня.
    run(session_factory, t0 + 3 * DAY + timedelta(hours=1))
    run(session_factory, t0 + 4 * DAY + timedelta(hours=1))
    run(session_factory, t0 + 4 * DAY + timedelta(hours=2))
    assert [subj for _, subj, _ in letters][2:] == ["Капсулка: осталось 2 дня на выбор состава семьи", "Капсулка: осталось 1 день на выбор состава семьи"]
    assert all(to == "nikita@example.com" for to, _, _ in letters)
    assert all("http" not in text for _, _, text in letters)


def test_r13_t3_after_an_outage_only_the_latest_letter_goes(client, big, session_factory, letters):
    _, owner = big["owner"]
    t0 = T0_REAL()
    plus_ends(session_factory, owner["id"], t0)
    run(session_factory, t0 + 3 * DAY + timedelta(hours=5))  # прошло три дня без единого прохода
    assert [subj for _, subj, _ in letters] == ["Капсулка: осталось 2 дня на выбор состава семьи"]


def test_r13_t3_no_letters_for_a_family_that_fits_the_free_limits(client, session_factory, letters):
    h, owner = register(client)
    client.put("/api/admin/billing", headers=h, json={"enabled": True, "price_month": 199, "price_year": 1990, "trial_days": 0})
    client.put("/api/admin/compression", headers=h, json={"enabled": True})
    hm, _ = register(client, "mom@example.com", "Мама", invite=invite_of(client, h, fid(owner)))
    t0 = T0_REAL()
    plus_ends(session_factory, owner["id"], t0)
    for days in (0, 3, 4, 6):
        run(session_factory, t0 + days * DAY + timedelta(hours=1))
    assert letters == [] and me(client, h)["plus_ending"] is None
    assert len(client.get(f"/api/families/{fid(owner)}", headers=h).json()["members"]) == 2


def test_r13_t4_owner_chooses_who_stays_and_which_cabinets(client, big, session_factory, letters):
    h, owner = big["owner"]
    plus_ends(session_factory, owner["id"], T0_REAL())
    run(session_factory, datetime.now(timezone.utc))
    f = fid(owner)
    cab = cabinets(client, h)
    keep_people = [big["p4"][1]["id"], big["p5"][1]["id"]]  # не самые давние: выбор владельца важнее порядка
    keep_cabs = [cab["Н1"]["id"], cab["Н2"]["id"], cab["В1"]["id"]]
    r = client.post(f"/api/families/{f}/compress", headers=h, json={"keep_user_ids": keep_people, "keep_cabinet_ids": keep_cabs})
    assert r.status_code == 200, r.text
    assert sorted(m["name"] for m in r.json()["members"]) == ["Никита", "Пятая", "Четвёртый"]
    after = cabinets(client, h)
    assert {n for n, c in after.items() if c["status"] == "active"} == {"Н1", "Н2", "В1"}
    assert {n for n, c in after.items() if c["status"] == "frozen"} == {"Семья Никита", "П1", "Н3"}  # остальные заморожены, не удалены
    # Вторая и Третий в личных семьях со своими аптечками, кулдауна нет.
    for key in ("p2", "p3"):
        mine = me(client, big[key][0])["families"]
        assert len(mine) == 1 and mine[0]["role"] == "owner" and mine[0]["status"] == "active"
    # Выбранные владельцем аптечки уходящий не забирает: В1 (самая старая у Второй) осталась в семье, Вторая забрала В2.
    assert "В1" in after and "В2" not in after
    assert [x["name"] for x in me(client, big["p2"][0])["families"]] == ["В2"]
    assert [x["name"] for x in me(client, big["p3"][0])["families"]] == ["Т1"]
    # Уходящим пришло письмо, владельцу нет (выбор сделал он сам).
    assert sorted(to for to, subj, _ in letters if "перенесены" in subj) == ["p2@example.com", "p3@example.com"]
    check_household_invariants(session_factory)


@pytest.mark.parametrize("body,status", [
    ({"keep_user_ids": [], "keep_cabinet_ids": []}, 200),
    ({"keep_user_ids": ["p2", "p3", "p4"], "keep_cabinet_ids": []}, 422),  # трое и владелец: больше бесплатного
    ({"keep_user_ids": ["p2"], "keep_cabinet_ids": ["c1", "c2", "c3"]}, 422),  # двое людей, три аптечки: аптечек не больше людей
    ({"keep_user_ids": [999999], "keep_cabinet_ids": []}, 404),
])
def test_r13_t4_choice_is_validated(client, big, session_factory, body, status):
    h, owner = big["owner"]
    plus_ends(session_factory, owner["id"], T0_REAL())
    cab = list(cabinets(client, h).values())
    ids = {"p2": big["p2"][1]["id"], "p3": big["p3"][1]["id"], "p4": big["p4"][1]["id"]}
    body = {
        "keep_user_ids": [ids.get(x, x) for x in body["keep_user_ids"]],
        "keep_cabinet_ids": [cab[int(x[1:]) - 1]["id"] for x in body["keep_cabinet_ids"]],
    }
    assert client.post(f"/api/families/{fid(owner)}/compress", headers=h, json=body).status_code == status


def test_r13_t4_choice_rules(client, big, session_factory):
    h, owner = big["owner"]
    f = fid(owner)
    # Плюс идёт: выбирать нечего.
    assert client.post(f"/api/families/{f}/compress", headers=h, json={}).status_code == 409
    plus_ends(session_factory, owner["id"], T0_REAL())
    assert client.post(f"/api/families/{f}/compress", headers=big["p2"][0], json={}).status_code == 403  # только владелец
    # Сжатие выключено в админке: недоступно.
    client.put("/api/admin/compression", headers=h, json={"enabled": False})
    assert client.post(f"/api/families/{f}/compress", headers=h, json={}).status_code == 409


def test_r14_t1_t2_without_a_choice_the_oldest_stay_after_five_days(client, big, session_factory, letters):
    """BC13: через 5 дней остаются владелец и двое самых давних, уходящие в личных семьях, лишние аптечки заморожены."""
    h, owner = big["owner"]
    t0 = T0_REAL()
    plus_ends(session_factory, owner["id"], t0)
    with session_factory() as db:
        meds_before = db.scalar(select(func.count()).select_from(Medicine))
    run(session_factory, t0 + 5 * DAY + timedelta(hours=1))
    f = fid(owner)
    assert [m["name"] for m in client.get(f"/api/families/{f}", headers=h).json()["members"]] == ["Никита", "Вторая", "Третий"]
    # Четвёртый ничего не создавал: пустая аптечка. Пятая создала «П1» и забрала её с лекарством.
    p4, p5 = me(client, big["p4"][0])["families"], me(client, big["p5"][0])["families"]
    assert [(x["name"], x["role"]) for x in p4] == [("Семья Четвёртый", "owner")]
    assert [(x["name"], x["role"]) for x in p5] == [("П1", "owner")]
    assert [m["name"] for m in client.get(f"/api/families/{p5[0]['id']}/medicines", headers=big["p5"][0]).json()] == ["Лекарство П1"]
    assert client.get(f"/api/families/{p4[0]['id']}/medicines", headers=big["p4"][0]).json() == []
    # В семье осталось 7 аптечек: три самых давних активны (по числу людей), четыре заморожены.
    left = me(client, h)["families"]
    assert [(x["name"], x["status"]) for x in left] == [
        ("Семья Никита", "active"), ("В1", "active"), ("В2", "active"), ("Т1", "frozen"), ("Н1", "frozen"), ("Н2", "frozen"), ("Н3", "frozen"),
    ]
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Medicine)) == meds_before  # ничего не удалено
        kinds = [e.kind for e in db.scalars(select(HouseholdEvent).where(HouseholdEvent.user_id.in_([big["p4"][1]["id"], big["p5"][1]["id"]])))]
        assert kinds.count("compress") == 2  # в журнале: вынужденное отключение при сжатии
    # Письма: владельцу итог, каждому отключённому свой.
    moved = {to: text for to, subj, text in letters if "перенесены" in subj}
    assert sorted(moved) == ["p4@example.com", "p5@example.com"] and "«П1»" in moved["p5@example.com"] and "Ничего не удалено" in moved["p5@example.com"]
    done = [text for to, subj, text in letters if subj == "Капсулка: состав семьи сжат"]
    assert len(done) == 1 and "остались 3 человек, 2 перешли в личные семьи, 4 аптечек заморожены" in done[0]
    assert all("http" not in text for _, _, text in letters)
    check_household_invariants(session_factory)


def test_r14_t3_t5_frozen_cabinet_can_only_be_viewed_and_exported(client, big, session_factory):
    h, owner = big["owner"]
    t0 = T0_REAL()
    plus_ends(session_factory, owner["id"], t0)
    run(session_factory, t0 + 5 * DAY + timedelta(hours=1))
    frozen = next(x for x in me(client, h)["families"] if x["name"] == "Н3")
    fz = frozen["id"]
    meds = client.get(f"/api/families/{fz}/medicines", headers=h)
    assert meds.status_code == 200 and [m["name"] for m in meds.json()] == ["Лекарство Н3"]  # просмотр
    assert client.get(f"/api/families/{fz}/export.txt", headers=h).status_code == 200  # выгрузка
    mid = meds.json()[0]["id"]
    for request, args in (
        (client.post, (f"/api/families/{fz}/medicines", {"name": "Новое"})),
        (client.patch, (f"/api/families/{fz}/medicines/{mid}", {"name": "Другое"})),
        (client.delete, (f"/api/families/{fz}/medicines/{mid}", None)),
        (client.post, (f"/api/families/{fz}/medicines/{mid}/consume", {})),  # отметить приём
        (client.post, (f"/api/families/{fz}/schedule", {"medicine_id": mid, "times": [480]})),  # расписание
    ):
        r = request(args[0], headers=h, **({"json": args[1]} if args[1] is not None else {}))
        assert r.status_code == 409 and "заморожена" in r.json()["detail"], (args[0], r.status_code, r.text)
    # Удалить замороженную аптечку целиком создатель или владелец может.
    assert client.delete(f"/api/families/{fz}", headers=h).status_code == 204


def test_r14_t4_plus_unfreezes_everything_and_removed_people_can_be_invited_again(client, big, session_factory, letters):
    """BC14: Плюс снова оплачен, заморозка снята, отключённых можно пригласить заново."""
    h, owner = big["owner"]
    t0 = T0_REAL()
    plus_ends(session_factory, owner["id"], t0)
    run(session_factory, t0 + 5 * DAY + timedelta(hours=1))
    assert {x["status"] for x in me(client, h)["families"]} == {"active", "frozen"}
    grant_plus(client, h, fid(owner))  # Плюс снова есть (оплата делает то же самое)
    assert {x["status"] for x in me(client, h)["families"]} == {"active"}
    with session_factory() as db:
        house = db.get(User, owner["id"]).household
        assert (house.plus_ended_at, house.compress_stage) == (None, 0)
    run(session_factory, t0 + 6 * DAY)  # повторный проход ничего не возвращает и ничего не ломает
    assert len(client.get(f"/api/families/{fid(owner)}", headers=h).json()["members"]) == 3
    # Четвёртого владелец приглашает снова: он приносит свою (пустую) аптечку или она растворяется, кулдауна нет.
    r = client.post("/api/families/join", headers=big["p4"][0], json={"code": invite_of(client, h, fid(owner))})
    assert r.status_code == 200, r.text
    assert len(client.get(f"/api/families/{fid(owner)}", headers=h).json()["members"]) == 4
    check_household_invariants(session_factory)


def test_r14_t6_compression_is_idempotent(client, big, session_factory, letters):
    h, owner = big["owner"]
    t0 = T0_REAL()
    plus_ends(session_factory, owner["id"], t0)
    assert run(session_factory, t0 + 5 * DAY + timedelta(hours=1)) == 1
    snapshot = [(x["name"], x["status"]) for x in me(client, h)["families"]], len(letters)
    assert run(session_factory, t0 + 5 * DAY + timedelta(hours=2)) == 0
    assert run(session_factory, t0 + 9 * DAY) == 0
    assert ([(x["name"], x["status"]) for x in me(client, h)["families"]], len(letters)) == snapshot


def test_r14_payment_during_the_window_cancels_the_compression(client, big, session_factory, letters):
    h, owner = big["owner"]
    t0 = T0_REAL()
    plus_ends(session_factory, owner["id"], t0)
    run(session_factory, t0 + 3 * DAY + timedelta(hours=1))
    grant_plus(client, h, fid(owner))
    run(session_factory, t0 + 6 * DAY)
    assert len(client.get(f"/api/families/{fid(owner)}", headers=h).json()["members"]) == 5
    assert {x["status"] for x in me(client, h)["families"]} == {"active"} and len(me(client, h)["families"]) == 8


def test_bc15_refund_starts_the_five_days_from_the_moment_of_refund(client, big, session_factory, letters):
    """Возврат денег закрывает Плюс сразу (R15), и от этого момента идут те же 5 дней."""
    h, owner = big["owner"]
    refunded_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    plus_ends(session_factory, owner["id"], refunded_at)  # так возврат записывает конец Плюса (payments.end_plus)
    run(session_factory, refunded_at + DAY)
    assert [subj for _, subj, _ in letters] == ["Капсулка: Плюс вашей семьи закончился"]
    assert len(client.get(f"/api/families/{fid(owner)}", headers=h).json()["members"]) == 5
    run(session_factory, refunded_at + 5 * DAY + timedelta(minutes=2))
    assert len(client.get(f"/api/families/{fid(owner)}", headers=h).json()["members"]) == 3


def test_admin_removing_plus_starts_the_window_now(client, big, session_factory, letters):
    h, owner = big["owner"]
    assert client.put(f"/api/admin/users/{owner['id']}/plan", headers=h, json={"plan": "free"}).status_code == 200
    with session_factory() as db:
        house = db.get(User, owner["id"]).household
        assert house.plus_ended_at is not None and house.plan == "free"
    now = datetime.now(timezone.utc)
    run(session_factory, now + timedelta(hours=1))
    assert [subj for _, subj, _ in letters] == ["Капсулка: Плюс вашей семьи закончился"]
    run(session_factory, now + 5 * DAY + timedelta(hours=1))
    assert len(client.get(f"/api/families/{fid(owner)}", headers=h).json()["members"]) == 3


def test_flag_off_changes_nothing_and_thaws_what_was_frozen(client, big, session_factory, letters):
    h, owner = big["owner"]
    t0 = T0_REAL()
    plus_ends(session_factory, owner["id"], t0)
    run(session_factory, t0 + 5 * DAY + timedelta(hours=1))
    assert "frozen" in {x["status"] for x in me(client, h)["families"]}
    assert client.put("/api/admin/compression", headers=h, json={"enabled": False}).json() == {"enabled": False}
    letters.clear()
    assert run(session_factory, t0 + 6 * DAY) == 4  # четыре замороженные аптечки снова активны: возврат к прежнему поведению
    assert {x["status"] for x in me(client, h)["families"]} == {"active"} and letters == []
    assert me(client, h)["plus_ending"] is None


def test_compression_is_off_by_default(client):
    h, _ = register(client)
    assert client.get("/api/admin/compression", headers=h).json() == {"enabled": False}


def test_flag_off_nothing_happens_after_plus_ends(client, big, session_factory, letters):
    h, owner = big["owner"]
    client.put("/api/admin/compression", headers=h, json={"enabled": False})
    t0 = T0_REAL()
    plus_ends(session_factory, owner["id"], t0)
    assert run(session_factory, t0 + 9 * DAY) == 0
    assert len(client.get(f"/api/families/{fid(owner)}", headers=h).json()["members"]) == 5 and letters == []
    assert {x["status"] for x in me(client, h)["families"]} == {"active"} and me(client, h)["plus_ending"] is None


def test_compression_setting_is_for_admin_only(client):
    h, _ = register(client)
    hm, _ = register(client, "other@example.com", "Другой")
    assert client.put("/api/admin/compression", headers=hm, json={"enabled": True}).status_code == 403
    assert client.get("/api/admin/compression", headers=hm).status_code == 403


def test_r14_owner_can_unfreeze_one_cabinet_only_when_there_is_room(client, big, session_factory):
    h, owner = big["owner"]
    t0 = T0_REAL()
    plus_ends(session_factory, owner["id"], t0)
    run(session_factory, t0 + 5 * DAY + timedelta(hours=1))
    cab = cabinets(client, h)
    frozen, active = cab["Н1"]["id"], cab["В1"]["id"]
    assert client.post(f"/api/families/{frozen}/unfreeze", headers=big["p2"][0]).status_code == 403  # только владелец
    r = client.post(f"/api/families/{frozen}/unfreeze", headers=h)
    assert r.status_code == 409 and "Свободного места" in r.json()["detail"]
    assert client.delete(f"/api/families/{active}", headers=h).status_code == 204  # освободили место
    r = client.post(f"/api/families/{frozen}/unfreeze", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "active"
    assert client.post(f"/api/families/{frozen}/unfreeze", headers=h).status_code == 409  # уже активна
    check_household_invariants(session_factory)


def test_r14_frozen_cabinets_do_not_count_in_the_active_limit(client, big, session_factory):
    h, owner = big["owner"]
    t0 = T0_REAL()
    plus_ends(session_factory, owner["id"], t0)
    run(session_factory, t0 + 5 * DAY + timedelta(hours=1))
    # Активных ровно по числу людей (3), замороженные не мешают лимиту, но и новую завести нельзя.
    assert client.post("/api/families", headers=h, json={"name": "Ещё"}).status_code == 402
    active = [x for x in me(client, h)["families"] if x["status"] == "active"]
    assert len(active) == 3
    assert client.delete(f"/api/families/{active[-1]['id']}", headers=h).status_code == 204
    assert client.post("/api/families", headers=h, json={"name": "Ещё"}).status_code == 201


# --- семьи, где было четверо до 13.10.2026 (Соглашение п. 6.12) ---
def kept_four(session_factory, uid):
    with session_factory() as db:
        return db.get(User, uid).household.kept_four


def test_four_people_before_the_new_terms_are_remembered_and_stay_four(client, big, session_factory, letters):
    """Семье, где уже было четверо, после окончания Плюса остаются четверо, а не трое; пятый уходит."""
    h, owner = big["owner"]
    with session_factory() as db:
        db.get(User, owner["id"]).household.kept_four = True
        db.commit()
    t0 = T0_REAL()
    plus_ends(session_factory, owner["id"], t0)
    assert client.get("/api/auth/me", headers=h).json()["plus_ending"]["people_limit"] == 4
    run(session_factory, t0 + 5 * DAY + timedelta(hours=1))
    f = fid(owner)
    assert [m["name"] for m in client.get(f"/api/families/{f}", headers=h).json()["members"]] == ["Никита", "Вторая", "Третий", "Четвёртый"]
    assert [x["name"] for x in me(client, big["p5"][0])["families"]] == ["П1"]  # ушла только пятая
    done = [text for to, subj, text in letters if subj == "Капсулка: состав семьи сжат"]
    assert len(done) == 1 and "остались 4 человек, 1 перешли в личные семьи" in done[0]
    # у четырёх активных аптечек будет не больше трёх (потолок бесплатной версии)
    assert sum(1 for x in me(client, h)["families"] if x["status"] == "active") == 3
    check_household_invariants(session_factory)


def test_owner_choice_may_keep_four_when_the_family_was_four(client, big, session_factory):
    h, owner = big["owner"]
    f = fid(owner)
    plus_ends(session_factory, owner["id"], T0_REAL())
    four = [big[k][1]["id"] for k in ("p2", "p3", "p4")]
    assert client.post(f"/api/families/{f}/compress", headers=h, json={"keep_user_ids": four}).status_code == 422  # трое по умолчанию
    with session_factory() as db:
        db.get(User, owner["id"]).household.kept_four = True
        db.commit()
    assert client.post(f"/api/families/{f}/compress", headers=h, json={"keep_user_ids": four}).status_code == 200
    assert len(client.get(f"/api/families/{f}", headers=h).json()["members"]) == 4


def test_fourth_person_before_the_new_terms_sets_the_flag_and_after_does_not(client, session_factory, monkeypatch):
    from app import households
    h, owner = register(client)
    f = fid(owner)
    grant_plus(client, h, f)
    for i, name in enumerate(("Вторая", "Третий"), start=2):
        register(client, f"q{i}@example.com", name, invite=invite_of(client, h, f))
    assert kept_four(session_factory, owner["id"]) is False  # трое: помнить нечего
    register(client, "q4@example.com", "Четвёртый", invite=invite_of(client, h, f))
    assert kept_four(session_factory, owner["id"]) is True  # до 13.10.2026 четверо: запомнили

    h2, owner2 = register(client, "late@example.com", "Поздний")
    f2 = fid(owner2)
    grant_plus(client, h, f2)  # Плюс выдаёт администратор (первый аккаунт)
    monkeypatch.setattr(households, "NEW_TERMS_FROM", datetime.now(timezone.utc) - DAY)  # новые условия уже действуют
    for i in range(3):
        register(client, f"late{i}@example.com", f"П{i}", invite=invite_of(client, h2, f2))
    assert kept_four(session_factory, owner2["id"]) is False


def test_letters_say_moscow_time_and_the_wording_asked_by_the_legal_review(client, big, session_factory, letters):
    h, owner = big["owner"]
    t0 = T0_REAL()
    plus_ends(session_factory, owner["id"], t0)
    run(session_factory, t0 + timedelta(minutes=1))   # письмо в день конца
    run(session_factory, t0 + 3 * DAY + DAY // 2)     # напоминание
    run(session_factory, t0 + 5 * DAY + timedelta(hours=1))  # сжатие
    with_dates = [text for _, subj, text in letters if "заканчивается" in subj or "закончился" in subj or "осталось" in subj]
    assert len(with_dates) >= 2 and all("по московскому времени" in text for text in with_dates)
    ended = next(text for _, subj, text in letters if subj == "Капсулка: Плюс вашей семьи закончился")
    assert "После оплаты Плюса заморозка снимается сразу" in ended and "Продлите Плюс, и заморозка" not in ended
    moved = [text for _, subj, text in letters if "перенесены" in subj]
    assert moved and all("Если вы не согласны, ответьте на это письмо" in text for text in moved)

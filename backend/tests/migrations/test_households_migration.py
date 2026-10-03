"""Миграция «семья и аптечки» (BC25): старые данные становятся семьями, ничего не теряется, конфликты останавливают миграцию."""
import os

import pytest
from alembic import command
from sqlalchemy import text

from tests.migrations.test_alembic import alembic  # noqa: F401  фикстура с настроенным Alembic

BEFORE = "c5e7a9b1d3f4"  # последняя миграция до семей


def add_user(conn, uid, plan="free", until=None, trial=None):
    conn.execute(text(
        "INSERT INTO users (id, email, name, password_hash, is_admin, token_version, created_at, plan, plus_until, trial_granted_at) "
        f"VALUES ({uid}, 'u{uid}@example.com', 'U{uid}', 'x', :admin, 0, '2026-01-01', :plan, :until, :trial)"
    ), {"admin": False, "plan": plan, "until": until, "trial": trial})


def add_family(conn, fid, name, code):
    conn.execute(text(f"INSERT INTO families (id, name, invite_code, created_at) VALUES ({fid}, '{name}', '{code}', '2026-01-0{fid}')"))


def add_member(conn, fid, uid, role, joined):
    conn.execute(text(
        f"INSERT INTO memberships (family_id, user_id, role, joined_at) VALUES ({fid}, {uid}, '{role}', '{joined}')"))


def sync_sequences(conn):
    """Строки вставлены с явными id, а Postgres не двигает счётчик сам: подвигаем, как это делает импорт из SQLite."""
    if conn.dialect.name == "postgresql":
        for table in ("users", "families", "medicines", "payments"):
            conn.execute(text(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), (SELECT COALESCE(MAX(id), 1) FROM {table}))"))


def rows(engine, sql):
    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(text(sql)).all()]


def test_bc25_existing_data_becomes_households(alembic):  # noqa: F811
    cfg, engine = alembic
    command.upgrade(cfg, BEFORE)
    with engine.begin() as conn:
        add_user(conn, 1)
        add_user(conn, 2, plan="plus", until="2030-01-01")  # заплатил: оплата есть
        add_user(conn, 3)
        add_user(conn, 4, plan="plus", until="2026-01-06", trial="2026-01-01")  # только пробный, оплат нет
        add_user(conn, 5)  # аптечек нет совсем
        conn.execute(text("INSERT INTO payments (id, user_id, email, period, amount, status, created_at) "
                          "VALUES (1, 2, 'u2@example.com', 'month', 199, 'succeeded', '2026-02-01')"))
        add_family(conn, 1, "Дом", "AAAA1111")
        add_family(conn, 2, "Дача", "BBBB2222")
        add_family(conn, 3, "Чужая", "CCCC3333")
        add_family(conn, 4, "Ничья", "DDDD4444")  # без людей
        for fid in (1, 2):  # двое владельцев, самый давний второй из них не главный
            add_member(conn, fid, 1, "owner", "2026-01-01")
            add_member(conn, fid, 2, "owner", "2026-02-01")
            add_member(conn, fid, 3, "member", "2026-03-01")
        add_member(conn, 3, 4, "owner", "2026-01-01")
        conn.execute(text("INSERT INTO medicines (id, family_id, name, indications, contraindications, notes, unit, created_at, updated_at) "
                          "VALUES (1, 1, 'Нурофен', '', '', '', 'шт', '2026-01-01', '2026-01-01')"))
        sync_sequences(conn)

    command.upgrade(cfg, "head")

    users = rows(engine, "SELECT id, household_role FROM users ORDER BY id")
    assert [r[1] for r in users] == ["owner", "member", "member", "owner", "owner"]  # у нескольких владельцев остался самый давний
    houses = {r[0]: r for r in rows(engine, "SELECT u.id, h.id, h.plan, h.plus_until, h.plus_is_trial FROM users u JOIN households h ON h.id = u.household_id")}
    assert houses[1][1] == houses[2][1] == houses[3][1] and houses[4][1] != houses[1][1] and houses[5][1] not in (houses[1][1], houses[4][1])
    assert houses[1][2] == "plus" and str(houses[1][3]).startswith("2030-01-01") and not houses[1][4]  # Плюс человека стал Плюсом семьи
    assert houses[4][2] == "plus" and bool(houses[4][4]) is True  # пробный остался пробным
    assert houses[5][2] == "free"
    fams = rows(engine, "SELECT id, household_id, created_by_id FROM families ORDER BY id")
    assert fams[0][1] == fams[1][1] == houses[1][1] and fams[0][2] == 1 and fams[1][2] == 1
    assert fams[3][1] is None  # аптечка без людей осталась как была, ничего не удалено
    own = rows(engine, f"SELECT name, created_by_id FROM families WHERE household_id = {houses[5][1]}")
    assert own == [("Семья U5", 5)]  # человеку без аптечек создана личная
    roles = rows(engine, "SELECT family_id, user_id, role FROM memberships WHERE family_id IN (1, 2) ORDER BY family_id, user_id")
    assert roles == [(1, 1, "owner"), (1, 2, "member"), (1, 3, "member"), (2, 1, "owner"), (2, 2, "member"), (2, 3, "member")]
    assert rows(engine, "SELECT name FROM medicines") == [("Нурофен",)]  # лекарства на месте


def test_bc25_conflict_stops_the_migration_without_touching_data(alembic):  # noqa: F811
    """Двое в разных аптечках с разными людьми слить нельзя: один увидел бы чужую аптечку."""
    cfg, engine = alembic
    command.upgrade(cfg, BEFORE)
    with engine.begin() as conn:
        for uid in (1, 2, 3):
            add_user(conn, uid)
        add_family(conn, 1, "Дом", "AAAA1111")
        add_family(conn, 2, "Дача", "BBBB2222")
        add_member(conn, 1, 1, "owner", "2026-01-01")
        add_member(conn, 1, 2, "member", "2026-01-01")
        add_member(conn, 2, 1, "owner", "2026-01-01")  # человек 1 в двух семьях, а человека 2 во второй нет
        add_member(conn, 2, 3, "member", "2026-01-01")
    with pytest.raises(RuntimeError, match="Миграция семей остановлена"):
        command.upgrade(cfg, "head")
    assert rows(engine, "SELECT version_num FROM alembic_version") == [(BEFORE,)]
    assert len(rows(engine, "SELECT id FROM memberships")) == 4


def test_downgrade_returns_plus_to_the_owner(alembic):  # noqa: F811
    cfg, engine = alembic
    command.upgrade(cfg, BEFORE)
    with engine.begin() as conn:
        add_user(conn, 1)
        add_user(conn, 2)
        add_family(conn, 1, "Дом", "AAAA1111")
        add_member(conn, 1, 1, "owner", "2026-01-01")
        add_member(conn, 1, 2, "member", "2026-02-01")
    command.upgrade(cfg, "head")
    with engine.begin() as conn:
        conn.execute(text("UPDATE households SET plan = 'plus', plus_until = '2031-01-01'"))
    command.downgrade(cfg, BEFORE)
    assert [(r[0], r[1]) for r in rows(engine, "SELECT id, plan FROM users ORDER BY id")] == [(1, "plus"), (2, "free")]

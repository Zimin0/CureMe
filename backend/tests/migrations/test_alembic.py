"""Миграции Alembic.

На сервере схему создают именно миграции (`alembic upgrade head`), а тесты API
берут её из моделей (`create_all`). Если кто-то поменяет модель и забудет
миграцию, API-тесты пройдут, а на сервере всё сломается. Эти тесты ловят это.
"""

import os

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from app.config import get_settings
from app.db import Base, make_engine

BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def alembic(tmp_path, monkeypatch):
    url = os.environ.get("CUREME_TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'migrations.db'}"
    # env.py берёт адрес базы из настроек приложения
    monkeypatch.setattr(get_settings(), "database_url", url)
    cfg = Config(os.path.join(BACKEND, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND, "alembic"))
    engine = make_engine(url)
    Base.metadata.drop_all(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    yield cfg, engine
    command.downgrade(cfg, "base")
    engine.dispose()


def test_single_head():
    """Две «головы» бывают, когда две ветки добавили миграции параллельно."""
    cfg = Config(os.path.join(BACKEND, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND, "alembic"))
    assert len(ScriptDirectory.from_config(cfg).get_heads()) == 1


def test_upgrade_creates_all_tables(alembic):
    cfg, engine = alembic
    command.upgrade(cfg, "head")
    tables = set(inspect(engine).get_table_names())
    assert set(Base.metadata.tables) <= tables


def test_models_match_migrations(alembic):
    cfg, engine = alembic
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], f"Модели и миграции разошлись — нужна новая миграция: {diff}"


def test_downgrade_and_upgrade_again(alembic):
    """Каждую миграцию можно откатить и накатить снова (проверка шагами вниз и вверх)."""
    cfg, engine = alembic
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    command.upgrade(cfg, "head")
    assert "medicines" in inspect(engine).get_table_names()


def test_single_category_moves_to_link_table(alembic):
    """Миграция на несколько категорий переносит уже выбранную категорию, ничего не теряя."""
    cfg, engine = alembic
    command.upgrade(cfg, "c3a9e1f0ad01")
    with engine.begin() as conn:
        cat = conn.execute(text("SELECT id FROM categories ORDER BY id LIMIT 1")).scalar()
        conn.execute(text("INSERT INTO families (id, name, invite_code, created_at) VALUES (1, 'Семья', 'X1', '2026-01-01')"))
        conn.execute(text(
            "INSERT INTO medicines (id, family_id, category_id, name, indications, contraindications, notes, unit, created_at, updated_at) "
            "VALUES (1, 1, :c, 'Нурофен', '', '', '', 'шт', '2026-01-01', '2026-01-01'),"
            "       (2, 1, NULL, 'Бинт', '', '', '', 'шт', '2026-01-01', '2026-01-01')"
        ), {"c": cat})
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        links = conn.execute(text("SELECT medicine_id, category_id, position FROM medicine_categories")).all()
    assert [tuple(r) for r in links] == [(1, cat, 0)]
    assert "category_id" not in {c["name"] for c in inspect(engine).get_columns("medicines")}

    command.downgrade(cfg, "c3a9e1f0ad01")  # обратно основная категория возвращается в колонку
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, category_id FROM medicines ORDER BY id")).all()
    assert [tuple(r) for r in rows] == [(1, cat), (2, None)]

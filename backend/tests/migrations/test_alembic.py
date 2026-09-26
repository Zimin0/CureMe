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
from sqlalchemy import inspect

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

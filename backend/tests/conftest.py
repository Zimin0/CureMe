"""Общие фикстуры для всех уровней тестов.

Уровень теста определяется папкой, в которой он лежит:
  tests/unit/         — чистые функции, без базы и HTTP (маркер unit);
  tests/integration/  — настоящее приложение FastAPI + настоящая база (маркер integration);
  tests/migrations/   — миграции Alembic на пустой базе (маркер migrations).
Запуск одного уровня: `pytest -m unit`.

По умолчанию каждый тест получает свежую SQLite-базу во временной папке.
Если задать CUREME_TEST_DATABASE_URL (например, Postgres в CI), те же тесты
идут на этой базе: перед каждым тестом схема пересоздаётся.
"""

import os
import tempfile
from pathlib import Path

os.environ["CUREME_REMOTE_LOOKUP"] = "false"
os.environ["CUREME_RATE_LIMIT"] = "false"  # сотни регистраций с одного адреса; лимиты проверяет test_security_hardening.py
os.environ["CUREME_BACKGROUND_JOBS"] = "false"  # напоминания и Telegram-бот тесты вызывают напрямую
os.environ["CUREME_FRONTEND_DIST"] = "/nonexistent"
os.environ["CUREME_MEDIA_DIR"] = tempfile.mkdtemp()

import bcrypt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db, make_engine
from app.main import app

TEST_DATABASE_URL = os.environ.get("CUREME_TEST_DATABASE_URL")

# bcrypt специально медленный (~0.25 с на хеш) — это защита от перебора паролей.
# В тестах регистраций сотни, поэтому снижаем «стоимость» до минимума: алгоритм тот же.
_gensalt = bcrypt.gensalt
bcrypt.gensalt = lambda rounds=4, prefix=b"2b": _gensalt(rounds, prefix)
LEVELS = ("unit", "integration", "migrations")


def pytest_collection_modifyitems(items):
    for item in items:
        level = Path(str(item.fspath)).parent.name
        if level in LEVELS:
            item.add_marker(level)


@pytest.fixture(autouse=True)
def no_trial_by_default(monkeypatch):
    """Новые аккаунты в тестах бесплатные: пробный Плюс включает только test_trial.py (фикстура trial_on)."""
    monkeypatch.setattr("app.plans.DEFAULT_TRIAL_DAYS", 0)


@pytest.fixture
def engine(tmp_path):
    url = TEST_DATABASE_URL or f"sqlite:///{tmp_path / 'test.db'}"
    eng = make_engine(url)
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    if TEST_DATABASE_URL:
        Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def db(session_factory):
    """Сессия SQLAlchemy для тестов, которым нужна база без HTTP."""
    s = session_factory()
    yield s
    s.close()


@pytest.fixture
def client(session_factory):
    def override():
        s = session_factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def register(client, email="nikita@example.com", name="Никита", invite=None, password="secret123"):
    r = client.post("/api/auth/register", json={"email": email, "name": name, "password": password, "invite_code": invite, "consent": True})
    assert r.status_code == 201, r.text
    data = r.json()
    return {"Authorization": f"Bearer {data['access_token']}"}, data["user"]


def fid(user) -> int:
    return user["families"][0]["id"]


def grant_plus(client, h, family_id, plan="plus", until=None):
    """Админ (h) включает Плюс аккаунту главного владельца аптечки. Возвращает ответ API."""
    fam = next(x for x in client.get("/api/admin/families", headers=h).json() if x["id"] == family_id)
    r = client.put(f"/api/admin/users/{fam['owner_id']}/plan", headers=h, json={"plan": plan, "plus_until": until})
    assert r.status_code == 200, r.text
    return r


@pytest.fixture
def owner(client):
    """Зарегистрированный владелец семьи: (заголовки, пользователь, id семьи)."""
    h, u = register(client)
    return h, u, fid(u)

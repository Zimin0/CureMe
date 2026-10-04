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
from datetime import datetime, timedelta, timezone
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
def new_terms_in_force(monkeypatch):
    """Тесты проверяют правила новой редакции (3 человека); переходный период до 13 октября — в test_plans.py."""
    monkeypatch.setattr("app.plans.NEW_TERMS_FROM", datetime(2000, 1, 1, tzinfo=timezone.utc))


@pytest.fixture(autouse=True)
def no_switch_limits_by_default(monkeypatch):
    """Кулдаун смены семьи и счётчик смен за 30 дней (R11) в обычных сценариях выключены; их проверяет test_switch_rules.py."""
    monkeypatch.setattr("app.households.SWITCH_COOLDOWN_DAYS", 0)
    monkeypatch.setattr("app.households.CHANGES_PER_30D_FREE", 0)
    monkeypatch.setattr("app.households.CHANGES_PER_30D_PLUS", 0)


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


def register(client, email="nikita@example.com", name="Никита", invite=None, password="kapsula-secret-123"):
    r = client.post("/api/auth/register", json={"email": email, "name": name, "password": password, "invite_code": invite, "consent": True})
    assert r.status_code == 201, r.text
    data = r.json()
    return {"Authorization": f"Bearer {data['access_token']}"}, data["user"]


def invite_of(client, h, family_id) -> str:
    """Действующий код приглашения семьи (R04): у владельца он всегда есть, а сгоревший заменяется новым. Код одноразовый."""
    r = client.get(f"/api/families/{family_id}", headers=h)
    assert r.status_code == 200 and r.json()["invite_code"], r.text
    return r.json()["invite_code"]


def fid(user) -> int:
    return user["families"][0]["id"]


def hand_over(client, h_from, family_id, to_user_id, h_to):
    """Передача владения по правилам R23: предложение владельца и согласие принимающего."""
    r = client.post(f"/api/families/{family_id}/owner-transfer", headers=h_from, json={"user_id": to_user_id})
    assert r.status_code == 201, r.text
    r = client.post(f"/api/families/{family_id}/owner-transfer/accept", headers=h_to)
    assert r.status_code == 200, r.text
    return r.json()


def age_owner_events(session_factory, days=8):
    """Сдвигает прошлые смены владельца в прошлое: кулдаун передачи (7 дней, R23-T5) уже закончился."""
    from sqlalchemy import select

    from app.models import HouseholdEvent

    with session_factory() as db:
        for e in db.scalars(select(HouseholdEvent).where(HouseholdEvent.kind == "owner")):
            e.created_at = e.created_at - timedelta(days=days)
        db.commit()


def check_household_invariants(session_factory):
    """Инварианты семей (R01–R03, R20-T3): у каждого человека одна семья, у семьи один владелец, лимиты, доступ = люди × аптечки.

    Вызывается в конце сценариев; сессия закрывается сразу, иначе на Postgres транзакция повисла бы на сносе схемы.
    """
    from app.households import invariant_problems

    with session_factory() as db:
        problems = invariant_problems(db)
    assert problems == [], problems


def grant_plus(client, h, family_id, plan="plus", until=None):
    """Админ (h) включает Плюс семье, которой принадлежит аптечка (через её владельца). Возвращает ответ API."""
    fam = next(x for x in client.get("/api/admin/families", headers=h).json() if x["id"] == family_id)
    r = client.put(f"/api/admin/users/{fam['owner_id']}/plan", headers=h, json={"plan": plan, "plus_until": until})
    assert r.status_code == 200, r.text
    return r


@pytest.fixture
def owner(client):
    """Зарегистрированный владелец семьи: (заголовки, пользователь, id семьи)."""
    h, u = register(client)
    return h, u, fid(u)

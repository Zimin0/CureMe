"""Перенос данных из SQLite в Postgres (app/sqlite_import.py).

Источник — всегда файл SQLite, приёмник — CUREME_TEST_DATABASE_URL (Postgres в CI)
или второй файл SQLite, если Postgres не задан.
"""
import os
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Base, make_engine
from app.models import Category, Family, Medicine, MedicineCategory, Membership, Package, ProductCode, User, UserMark
from app.seed import ensure_default_categories
from app.sqlite_import import import_sqlite


@pytest.fixture
def target_url(tmp_path):
    url = os.environ.get("CUREME_TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'target.db'}"
    eng = make_engine(url)
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    with Session(eng) as s:  # как после миграций: в новой базе уже есть стандартные категории
        ensure_default_categories(s)
        s.commit()
    yield url
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def sqlite_file(tmp_path):
    path = tmp_path / "cureme.db"
    eng = make_engine(f"sqlite:///{path}")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        eyes = Category(id=40, name="Глаза", icon="👁️", sort=0)
        admin = User(id=7, email="nikita@example.com", name="Никита", password_hash="h", is_admin=True)
        masha = User(id=9, email="masha@example.com", name="Маша", password_hash="h")
        fam = Family(id=3, name="Семья Никита", invite_code="ABC123")
        s.add_all([eyes, admin, masha, fam])
        s.flush()
        s.add_all([Membership(family=fam, user=admin, role="owner"), Membership(family=fam, user=masha)])
        med = Medicine(id=11, family=fam, category_links=[MedicineCategory(category=eyes)], name="Тауфон", dosage="4%", created_by_id=7)
        med.packages.append(Package(id=21, quantity=5.5, expiry_date=date(2030, 7, 31), batch="3589"))
        s.add_all([med, ProductCode(gtin="04605077018932", name="Ларингобакт", pack_size=30, source="internet")])
        s.flush()
        s.add(UserMark(user_id=9, medicine_id=11, is_favorite=True, helps_me=True, personal_note="мне помогает"))
        s.commit()
    eng.dispose()
    return path


def test_copies_everything_and_keeps_backup(sqlite_file, target_url):
    assert import_sqlite(sqlite_file, target_url) is True
    assert not sqlite_file.exists()
    assert len(list(sqlite_file.parent.glob("cureme.db.imported-*"))) == 1

    eng = make_engine(target_url)
    with Session(eng) as s:
        # стандартные категории новой базы заменены категориями из SQLite
        assert [c.name for c in s.scalars(select(Category))] == ["Глаза"]
        assert [(u.id, u.email, u.is_admin) for u in s.scalars(select(User).order_by(User.id))] == [
            (7, "nikita@example.com", True), (9, "masha@example.com", False)]
        med = s.get(Medicine, 11)
        assert (med.name, med.category.name, med.family.name) == ("Тауфон", "Глаза", "Семья Никита")
        assert [(p.quantity, p.expiry_date, p.batch) for p in med.packages] == [(5.5, date(2030, 7, 31), "3589")]
        mark = s.get(UserMark, (9, 11))
        assert (mark.is_favorite, mark.helps_me, mark.personal_note) == (True, True, "мне помогает")
        assert s.get(ProductCode, "04605077018932").pack_size == 30

        # новые записи получают id после перенесённых, а не 1 (иначе конфликт ключей)
        u = User(email="new@example.com", name="Новый", password_hash="h")
        c = Category(name="Зубы")
        s.add_all([u, c])
        s.commit()
        assert u.id == 10 and c.id == 41
    eng.dispose()


def test_skips_when_target_already_has_users(sqlite_file, target_url):
    assert import_sqlite(sqlite_file, target_url) is True
    backup = next(sqlite_file.parent.glob("cureme.db.imported-*"))
    backup.rename(sqlite_file)  # старый файл вернулся, а в Postgres уже живые данные
    assert import_sqlite(sqlite_file, target_url) is False
    assert sqlite_file.exists()


def test_nothing_to_import(tmp_path, target_url):
    assert import_sqlite(tmp_path / "missing.db", target_url) is False

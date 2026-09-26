"""global categories and admin role

Категории становятся общими для всех семей: одноимённые категории разных семей
сливаются в одну, лекарства переносятся на неё. Первый аккаунт становится администратором.

Revision ID: c3a9e1f0ad01
Revises: fb6d288afdbb
Create Date: 2026-09-26 20:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3a9e1f0ad01'
down_revision: Union[str, Sequence[str], None] = 'fb6d288afdbb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_CATEGORIES = [
    ("Обезболивающие", "🩹", "#e5484d"),
    ("Жаропонижающие", "🌡️", "#f76b15"),
    ("Простуда и ОРВИ", "🤧", "#0090ff"),
    ("Горло и кашель", "🗣️", "#8e4ec6"),
    ("Аллергия", "🌼", "#ffb224"),
    ("Желудок и кишечник", "🫄", "#30a46c"),
    ("Сердце и давление", "❤️", "#d6409f"),
    ("Раны и ожоги", "🩺", "#12a594"),
    ("Витамины", "🍊", "#f5a623"),
    ("Успокоительные и сон", "🌙", "#3e63dd"),
    ("Детское", "🧸", "#e54666"),
    ("Прочее", "💊", "#687076"),
]


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_admin', sa.Boolean(), server_default='0', nullable=False))

    conn = op.get_bind()
    first = conn.execute(sa.text("SELECT MIN(id) FROM users")).scalar()
    if first is not None:
        conn.execute(sa.text("UPDATE users SET is_admin = :t WHERE id = :id"), {"t": True, "id": first})

    # Сливаем одноимённые категории. Сравниваем в Python: lower() в SQLite не знает кириллицу.
    rows = conn.execute(sa.text("SELECT id, name, sort FROM categories ORDER BY id")).all()
    keep: dict[str, int] = {}
    for cid, name, _sort in rows:
        key = " ".join(name.split()).casefold()
        if key not in keep:
            keep[key] = cid
            continue
        conn.execute(sa.text("UPDATE medicines SET category_id = :keep WHERE category_id = :old"), {"keep": keep[key], "old": cid})
        conn.execute(sa.text("DELETE FROM categories WHERE id = :old"), {"old": cid})
    for cid, name, _sort in rows:
        if keep.get(" ".join(name.split()).casefold()) == cid:
            conn.execute(sa.text("UPDATE categories SET name = :n WHERE id = :id"), {"n": " ".join(name.split()), "id": cid})

    with op.batch_alter_table('categories', schema=None) as batch_op:
        batch_op.drop_index('ix_categories_family_id')
        batch_op.drop_column('family_id')
        batch_op.create_unique_constraint('uq_categories_name', ['name'])

    if not keep:
        cats = sa.table('categories', sa.column('name'), sa.column('icon'), sa.column('color'), sa.column('sort'))
        op.bulk_insert(cats, [
            {"name": n, "icon": i, "color": c, "sort": k} for k, (n, i, c) in enumerate(DEFAULT_CATEGORIES)
        ])


def downgrade() -> None:
    # Обратно категории привязываются к первой семье: разнести их по семьям уже нельзя.
    with op.batch_alter_table('categories', schema=None) as batch_op:
        batch_op.drop_constraint('uq_categories_name', type_='unique')
        batch_op.add_column(sa.Column('family_id', sa.Integer(), nullable=True))
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE categories SET family_id = (SELECT MIN(id) FROM families)"))
    with op.batch_alter_table('categories', schema=None) as batch_op:
        batch_op.create_foreign_key('fk_categories_family_id', 'families', ['family_id'], ['id'], ondelete='CASCADE')
        batch_op.create_index('ix_categories_family_id', ['family_id'], unique=False)
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('is_admin')

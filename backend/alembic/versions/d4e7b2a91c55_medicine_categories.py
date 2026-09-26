"""several categories per medicine

Лекарству можно поставить до трёх категорий: вместо колонки medicines.category_id
появляется таблица связей medicine_categories (многие ко многим). Уже выбранная
категория переносится в неё как основная (position = 0).

Revision ID: d4e7b2a91c55
Revises: c3a9e1f0ad01
Create Date: 2026-09-26 21:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e7b2a91c55'
down_revision: Union[str, Sequence[str], None] = 'c3a9e1f0ad01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'medicine_categories',
        sa.Column('medicine_id', sa.Integer(), nullable=False),
        sa.Column('category_id', sa.Integer(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['medicine_id'], ['medicines.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('medicine_id', 'category_id'),
    )
    with op.batch_alter_table('medicine_categories', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_medicine_categories_category_id'), ['category_id'], unique=False)

    # Переносим уже выбранные категории, ничего не теряя. JOIN отсекает «висячие» ссылки,
    # которые могли остаться в SQLite, если там не были включены внешние ключи.
    op.execute(
        "INSERT INTO medicine_categories (medicine_id, category_id, position) "
        "SELECT m.id, m.category_id, 0 FROM medicines m JOIN categories c ON c.id = m.category_id"
    )

    with op.batch_alter_table('medicines', schema=None) as batch_op:
        batch_op.drop_column('category_id')


def downgrade() -> None:
    # Обратно в одну колонку помещается только основная категория, остальные теряются.
    with op.batch_alter_table('medicines', schema=None) as batch_op:
        batch_op.add_column(sa.Column('category_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_medicines_category_id', 'categories', ['category_id'], ['id'], ondelete='SET NULL')
    op.execute(
        "UPDATE medicines SET category_id = ("
        "SELECT mc.category_id FROM medicine_categories mc "
        "WHERE mc.medicine_id = medicines.id ORDER BY mc.position LIMIT 1)"
    )
    with op.batch_alter_table('medicine_categories', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_medicine_categories_category_id'))
    op.drop_table('medicine_categories')

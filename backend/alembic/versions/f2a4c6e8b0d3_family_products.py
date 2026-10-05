"""family_products и восстановление пароля: правки людей в справочнике товаров только внутри аптечки, код сброса пароля

Revision ID: f2a4c6e8b0d3
Revises: b5d7f9a1c3e6
Create Date: 2026-10-04 19:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2a4c6e8b0d3'
down_revision: Union[str, Sequence[str], None] = 'b5d7f9a1c3e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'family_products',
        sa.Column('family_id', sa.Integer(), nullable=False),
        sa.Column('gtin', sa.String(length=14), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('form', sa.String(length=60), nullable=True),
        sa.Column('dosage', sa.String(length=60), nullable=True),
        sa.Column('active_ingredient', sa.String(length=200), nullable=True),
        sa.Column('manufacturer', sa.String(length=200), nullable=True),
        sa.Column('title', sa.String(length=300), nullable=True),
        sa.Column('unit', sa.String(length=20), nullable=True),
        sa.Column('pack_size', sa.Float(), nullable=True),
        sa.Column('blister_size', sa.Integer(), nullable=True),
        sa.Column('source', sa.String(length=30), server_default='user', nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['family_id'], ['families.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('family_id', 'gtin'),
    )
    op.add_column('users', sa.Column('reset_code_hash', sa.String(length=64), nullable=True))
    op.add_column('users', sa.Column('reset_sent_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('reset_attempts', sa.Integer(), server_default='0', nullable=False))
    # Из общего справочника записи людей (source = user) больше не читаются; сами строки не трогаем,
    # чтобы ничего не терять: безопасно откатиться можно без восстановления из копии.


def downgrade() -> None:
    op.drop_column('users', 'reset_attempts')
    op.drop_column('users', 'reset_sent_at')
    op.drop_column('users', 'reset_code_hash')
    op.drop_table('family_products')

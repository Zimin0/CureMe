"""household_invites: одноразовые приглашения в семью на 24 часа (R04)

Revision ID: b4d6f8a1c3e5
Revises: e8a1c3f5b7d9
Create Date: 2026-10-03 22:00:00

Только новая таблица, существующие данные не меняются. Прежние многоразовые коды аптечек (families.invite_code)
больше не принимаются: владелец выпускает новое приглашение на странице «Семья». Колонка families.invite_code
остаётся (мёртвая), убрать её можно отдельной миграцией позже.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4d6f8a1c3e5'
down_revision: Union[str, Sequence[str], None] = 'e8a1c3f5b7d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'household_invites',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('household_id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=32), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('used_by_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['household_id'], ['households.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['used_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_household_invites_household_id'), 'household_invites', ['household_id'], unique=False)
    op.create_index(op.f('ix_household_invites_code'), 'household_invites', ['code'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_household_invites_code'), table_name='household_invites')
    op.drop_index(op.f('ix_household_invites_household_id'), table_name='household_invites')
    op.drop_table('household_invites')

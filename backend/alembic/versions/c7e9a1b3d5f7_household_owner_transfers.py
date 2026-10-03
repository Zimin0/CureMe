"""household_owner_transfers: передача владения семьёй с согласием принимающего (R23)

Revision ID: c7e9a1b3d5f7
Revises: b4d6f8a1c3e5
Create Date: 2026-10-03 23:00:00

Новая таблица; записи о предложениях (кто, кому, чем закончилось) хранятся 30 дней после окончания срока
ответа и удаляются фоновой задачей.

Заодно чистится журнал семьи (R27): в detail убираются имена людей и названия аптечек (теперь там только
номера), удаляются записи семей, которых уже нет. Остальные данные не меняются.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7e9a1b3d5f7'
down_revision: Union[str, Sequence[str], None] = 'b4d6f8a1c3e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Журнал семьи: имена и названия аптечек в detail (с версии 1.21.0) стираем, записи исчезнувших семей удаляем.
    op.execute("UPDATE household_events SET detail = '' WHERE kind IN ('owner', 'cabinet_add', 'cabinet_delete')")
    op.execute("DELETE FROM household_events WHERE household_id IS NULL")
    op.create_table(
        'household_owner_transfers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('household_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('from_user_id', sa.Integer(), nullable=True),
        sa.Column('to_user_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=16), server_default='pending', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['household_id'], ['households.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['from_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['to_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_household_owner_transfers_household_id'), 'household_owner_transfers', ['household_id'], unique=False)
    op.create_index(op.f('ix_household_owner_transfers_to_user_id'), 'household_owner_transfers', ['to_user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_household_owner_transfers_to_user_id'), table_name='household_owner_transfers')
    op.drop_index(op.f('ix_household_owner_transfers_household_id'), table_name='household_owner_transfers')
    op.drop_table('household_owner_transfers')

"""trial_granted: отметка о выданном пробном Плюсе

Revision ID: a3c5e7b9d1f2
Revises: e7b2c4d6f8a1
Create Date: 2026-10-01 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3c5e7b9d1f2'
down_revision: Union[str, Sequence[str], None] = 'e7b2c4d6f8a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # У действующих аккаунтов пусто: пробный Плюс только для новых регистраций.
    op.add_column('users', sa.Column('trial_granted_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'trial_granted_at')

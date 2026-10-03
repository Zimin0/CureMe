"""users.household_changed_at: кулдаун смены семьи (R11)

Revision ID: f3c5e7a9b1d4
Revises: e1a3c5d7f9b2
Create Date: 2026-10-04 13:00:00

Одна необязательная колонка у человека: когда он сам сменил семью. Пусто у всех: кулдаун ни у кого не идёт.
Прежняя версия кода колонку не читает, откат безопасен.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3c5e7a9b1d4'
down_revision: Union[str, Sequence[str], None] = 'e1a3c5d7f9b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users') as batch:
        batch.add_column(sa.Column('household_changed_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('users') as batch:
        batch.drop_column('household_changed_at')

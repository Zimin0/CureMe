"""users.time_presets: своё время быстрых кнопок «Утро, День, Вечер, На ночь» в расписании

Revision ID: e5a7b9c1d3f6
Revises: d4f6a8c0e2b4
Create Date: 2026-10-13 20:00:00

Одна необязательная колонка. Пусто — стандартное время. Прежняя версия кода колонку не читает, откат безопасен.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5a7b9c1d3f6'
down_revision: Union[str, Sequence[str], None] = 'd4f6a8c0e2b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users') as batch:
        batch.add_column(sa.Column('time_presets', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('users') as batch:
        batch.drop_column('time_presets')

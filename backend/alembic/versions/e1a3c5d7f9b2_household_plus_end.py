"""households.plus_ended_at, compress_stage, kept_four: окончание Плюса и сжатие семьи (R13, R14)

Revision ID: e1a3c5d7f9b2
Revises: d8f0b2c4e6a8
Create Date: 2026-10-04 12:00:00

Три новые колонки у семьи, ничего не удаляется. plus_ended_at и compress_stage: у всех семей «Плюс не терялся»
(пусто и 0). kept_four: семьям, где сейчас четверо и больше, ставится «да» (Соглашение п. 6.12: после окончания Плюса
им остаются четверо, а не трое); остальным «нет». Прежняя версия кода колонки не читает, откат безопасен. Само поведение включается отдельной настройкой в админке
и по умолчанию выключено.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1a3c5d7f9b2'
down_revision: Union[str, Sequence[str], None] = 'd8f0b2c4e6a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('households') as batch:
        batch.add_column(sa.Column('plus_ended_at', sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column('compress_stage', sa.Integer(), server_default='0', nullable=False))
        batch.add_column(sa.Column('kept_four', sa.Boolean(), server_default='0', nullable=False))
    op.execute(sa.text(
        "UPDATE households SET kept_four = :yes "
        "WHERE (SELECT COUNT(*) FROM users WHERE users.household_id = households.id) >= 4"
    ).bindparams(sa.bindparam('yes', True, type_=sa.Boolean())))


def downgrade() -> None:
    with op.batch_alter_table('households') as batch:
        batch.drop_column('kept_four')
        batch.drop_column('compress_stage')
        batch.drop_column('plus_ended_at')

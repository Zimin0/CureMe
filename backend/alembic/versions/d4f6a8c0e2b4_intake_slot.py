"""intakes.slot_id, slot_date: какой приём из расписания закрыт нажатием «Принял(а)»

Revision ID: d4f6a8c0e2b4
Revises: c9e1a3b5d7f2
Create Date: 2026-10-13 19:00:00

Две необязательные колонки без значений по умолчанию. Старые записи остаются как были.
Прежняя версия кода колонки не читает, откат безопасен.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4f6a8c0e2b4'
down_revision: Union[str, Sequence[str], None] = 'c9e1a3b5d7f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('intakes') as batch:
        batch.add_column(sa.Column('slot_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('slot_date', sa.Date(), nullable=True))
        batch.create_index('ix_intakes_slot_id', ['slot_id'])


def downgrade() -> None:
    with op.batch_alter_table('intakes') as batch:
        batch.drop_index('ix_intakes_slot_id')
        batch.drop_column('slot_date')
        batch.drop_column('slot_id')

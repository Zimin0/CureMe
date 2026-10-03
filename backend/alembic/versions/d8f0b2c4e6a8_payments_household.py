"""payments.household_id: платёж записывается на семью, которой он продлевает Плюс (R06)

Revision ID: d8f0b2c4e6a8
Revises: c7e9a1b3d5f7
Create Date: 2026-10-04 09:00:00

Новая необязательная колонка, ничего не удаляется: прежняя версия кода колонку не читает, откат безопасен.
Уже созданные платежи привязываются к семье, в которой сейчас состоит плательщик (раньше Плюс уходил
семье плательщика на момент уведомления об оплате, то есть ровно к ней).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8f0b2c4e6a8'
down_revision: Union[str, Sequence[str], None] = 'c7e9a1b3d5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('payments') as batch:
        batch.add_column(sa.Column('household_id', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_payments_household_id', 'households', ['household_id'], ['id'], ondelete='SET NULL')
        batch.create_index(op.f('ix_payments_household_id'), ['household_id'], unique=False)
    op.execute(
        "UPDATE payments SET household_id = (SELECT household_id FROM users WHERE users.id = payments.user_id) "
        "WHERE user_id IS NOT NULL"
    )


def downgrade() -> None:
    with op.batch_alter_table('payments') as batch:
        batch.drop_index(op.f('ix_payments_household_id'))
        batch.drop_constraint('fk_payments_household_id', type_='foreignkey')
        batch.drop_column('household_id')

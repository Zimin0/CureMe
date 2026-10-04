"""схема полок аптечки и место лекарства на ней

Revision ID: a4e6c8b0d2f4
Revises: f3c5e7a9b1d4
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a4e6c8b0d2f4'
down_revision: Union[str, Sequence[str], None] = 'f3c5e7a9b1d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('families', sa.Column('shelf_plan', sa.Text(), nullable=True))
    for col in ('place_x', 'place_y', 'place_r'):
        op.add_column('medicines', sa.Column(col, sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('medicines') as b:
        for col in ('place_x', 'place_y', 'place_r'):
            b.drop_column(col)
    with op.batch_alter_table('families') as b:
        b.drop_column('shelf_plan')

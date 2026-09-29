"""family plan: тариф семьи «Бесплатный» / «Плюс»

Revision ID: b8e2f4a6c1d9
Revises: a2d9e4b7c1f3
Create Date: 2026-09-29 23:40:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8e2f4a6c1d9'
down_revision: Union[str, Sequence[str], None] = 'a2d9e4b7c1f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('families', schema=None) as batch_op:
        batch_op.add_column(sa.Column('plan', sa.String(length=16), server_default='free', nullable=False))
        batch_op.add_column(sa.Column('plus_until', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('families', schema=None) as batch_op:
        batch_op.drop_column('plus_until')
        batch_op.drop_column('plan')

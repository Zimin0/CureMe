"""user token_version: смена пароля отзывает старые токены

Revision ID: e5c1a7f3b9d2
Revises: a7d3f9c2e14b
Create Date: 2026-09-27 07:10:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5c1a7f3b9d2'
down_revision: Union[str, Sequence[str], None] = 'a7d3f9c2e14b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('token_version', sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('token_version')

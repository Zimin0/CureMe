"""site_stats: обезличенный подсчёт заходов на сайт (без cookie, IP и идентификатора посетителя)

Revision ID: b7d9f1a3c5e2
Revises: a6c8e0b2d4f1
Create Date: 2026-10-12 22:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7d9f1a3c5e2'
down_revision: Union[str, Sequence[str], None] = 'a6c8e0b2d4f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'site_stats',
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('key', sa.String(length=80), server_default='', nullable=False),
        sa.Column('count', sa.Integer(), server_default='0', nullable=False),
        sa.PrimaryKeyConstraint('day', 'kind', 'key'),
    )


def downgrade() -> None:
    op.drop_table('site_stats')

"""app settings (indication hints)

Revision ID: a7d3f9c2e14b
Revises: d4e7b2a91c55
Create Date: 2026-09-27 07:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7d3f9c2e14b'
down_revision: Union[str, Sequence[str], None] = 'd4e7b2a91c55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Пустая таблица: пока администратор ничего не менял, действуют значения по умолчанию из seed.py.
    op.create_table(
        'app_settings',
        sa.Column('key', sa.String(length=60), nullable=False),
        sa.Column('value', sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint('key'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('app_settings')

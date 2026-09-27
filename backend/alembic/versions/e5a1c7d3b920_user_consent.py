"""user consent to personal data processing

Revision ID: e5a1c7d3b920
Revises: a7d3f9c2e14b
Create Date: 2026-09-27 07:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5a1c7d3b920'
down_revision: Union[str, Sequence[str], None] = 'a7d3f9c2e14b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # У уже зарегистрированных согласия нет (NULL): приложение попросит его при следующем входе.
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('consent_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('consent_version', sa.String(length=20), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('consent_version')
        batch_op.drop_column('consent_at')

"""notification_prefs.notify_expired: отдельная галочка «срок уже истёк»

Revision ID: b5d7f9a1c3e6
Revises: a4e6c8b0d2f4
Create Date: 2026-10-05 10:00:00

Раньше одна галочка notify_expiry отвечала и за «скоро истечёт», и за «уже истёк». Теперь «уже истёк» — своя колонка.
У существующих строк значение копируется из notify_expiry, так что никому ничего не включается и не выключается.
Прежняя версия кода колонку не читает, откат безопасен.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b5d7f9a1c3e6'
down_revision: Union[str, Sequence[str], None] = 'a4e6c8b0d2f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('notification_prefs') as batch:
        batch.add_column(sa.Column('notify_expired', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.execute("UPDATE notification_prefs SET notify_expired = notify_expiry")


def downgrade() -> None:
    with op.batch_alter_table('notification_prefs') as batch:
        batch.drop_column('notify_expired')

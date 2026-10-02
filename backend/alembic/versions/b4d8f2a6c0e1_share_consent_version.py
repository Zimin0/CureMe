"""schedule_prefs: редакция отдельного разрешения сообщать доверенному

Revision ID: b4d8f2a6c0e1
Revises: a3c5e7b9d1f2
Create Date: 2026-10-02 20:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b4d8f2a6c0e1'
down_revision: Union[str, Sequence[str], None] = 'a3c5e7b9d1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('schedule_prefs') as b:
        b.add_column(sa.Column('escalate_consent_version', sa.String(length=32), nullable=True))
    # Уже данные разрешения относятся к прежней формулировке: помечаем редакцией «до отдельного согласия».
    op.execute("UPDATE schedule_prefs SET escalate_consent_version = 'legacy-p4.1' WHERE escalate_consent_at IS NOT NULL")


def downgrade() -> None:
    with op.batch_alter_table('schedule_prefs') as b:
        b.drop_column('escalate_consent_version')

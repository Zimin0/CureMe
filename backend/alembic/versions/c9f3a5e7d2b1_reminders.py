"""reminders: настройки напоминаний (почта, Telegram) и отправленные напоминания

Revision ID: c9f3a5e7d2b1
Revises: b8e2f4a6c1d9
Create Date: 2026-09-30 00:10:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9f3a5e7d2b1'
down_revision: Union[str, Sequence[str], None] = 'b8e2f4a6c1d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'notification_prefs',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('email_enabled', sa.Boolean(), nullable=False),
        sa.Column('telegram_enabled', sa.Boolean(), nullable=False),
        sa.Column('telegram_chat_id', sa.BigInteger(), nullable=True),
        sa.Column('telegram_name', sa.String(length=100), nullable=True),
        sa.Column('telegram_code_hash', sa.String(length=64), nullable=True),
        sa.Column('telegram_code_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('telegram_consent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notify_low', sa.Boolean(), nullable=False),
        sa.Column('notify_expiry', sa.Boolean(), nullable=False),
        sa.Column('expiry_days', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id'),
        sa.UniqueConstraint('telegram_chat_id'),
    )
    with op.batch_alter_table('notification_prefs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_notification_prefs_telegram_code_hash'), ['telegram_code_hash'], unique=True)
    op.create_table(
        'reminders_sent',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('ref_id', sa.Integer(), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'kind', 'ref_id'),
    )
    with op.batch_alter_table('reminders_sent', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_reminders_sent_user_id'), ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_table('reminders_sent')
    op.drop_table('notification_prefs')

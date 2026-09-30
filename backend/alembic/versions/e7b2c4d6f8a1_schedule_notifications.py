"""schedule notifications: настройки, доверенный человек, журнал отправленных

Revision ID: e7b2c4d6f8a1
Revises: d1a4f7c9e2b6
Create Date: 2026-09-30 23:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7b2c4d6f8a1'
down_revision: Union[str, Sequence[str], None] = 'd1a4f7c9e2b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'schedule_prefs',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('lead_minutes', sa.Integer(), nullable=False),
        sa.Column('repeat_minutes', sa.Integer(), nullable=False),
        sa.Column('escalate_enabled', sa.Boolean(), nullable=False),
        sa.Column('escalate_minutes', sa.Integer(), nullable=False),
        sa.Column('share_medicine_name', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id'),
    )
    op.create_table(
        'trusted_contacts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('email', sa.String(length=254), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('nonce', sa.String(length=32), nullable=False),
        sa.Column('consent_version', sa.String(length=32), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('request_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
    )
    op.create_table(
        'schedule_notified',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('slot_id', sa.Integer(), nullable=False),
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('stage', sa.String(length=16), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['slot_id'], ['schedule_slots.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slot_id', 'day', 'stage'),
    )
    op.create_index(op.f('ix_schedule_notified_user_id'), 'schedule_notified', ['user_id'])
    op.create_index(op.f('ix_schedule_notified_sent_at'), 'schedule_notified', ['sent_at'])


def downgrade() -> None:
    op.drop_table('schedule_notified')
    op.drop_table('trusted_contacts')
    op.drop_table('schedule_prefs')

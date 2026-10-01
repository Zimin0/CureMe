"""schedule: расписание приёма лекарств (назначения и их слоты «день недели + время»)

Revision ID: d1a4f7c9e2b6
Revises: c9f3a5e7d2b1
Create Date: 2026-09-30 22:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1a4f7c9e2b6'
down_revision: Union[str, Sequence[str], None] = 'd8b4e6a2f1c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'schedules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('family_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('medicine_id', sa.Integer(), nullable=True),
        sa.Column('medicine_name', sa.String(length=200), nullable=False),
        sa.Column('unit', sa.String(length=20), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('every_weeks', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['family_id'], ['families.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['medicine_id'], ['medicines.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_schedules_family_id'), 'schedules', ['family_id'])
    op.create_index(op.f('ix_schedules_user_id'), 'schedules', ['user_id'])
    op.create_index(op.f('ix_schedules_medicine_id'), 'schedules', ['medicine_id'])
    op.create_table(
        'schedule_slots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('schedule_id', sa.Integer(), nullable=False),
        sa.Column('weekday', sa.Integer(), nullable=False),
        sa.Column('minute', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['schedule_id'], ['schedules.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('schedule_id', 'weekday', 'minute'),
    )
    op.create_index(op.f('ix_schedule_slots_schedule_id'), 'schedule_slots', ['schedule_id'])


def downgrade() -> None:
    op.drop_table('schedule_slots')
    op.drop_table('schedules')

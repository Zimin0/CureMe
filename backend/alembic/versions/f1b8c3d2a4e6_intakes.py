"""intakes: история приёма лекарств

Revision ID: f1b8c3d2a4e6
Revises: e5c1a7f3b9d2
Create Date: 2026-09-28 21:40:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1b8c3d2a4e6'
down_revision: Union[str, Sequence[str], None] = 'e5c1a7f3b9d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'intakes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('family_id', sa.Integer(), nullable=False),
        sa.Column('medicine_id', sa.Integer(), nullable=True),
        sa.Column('medicine_name', sa.String(length=200), nullable=False),
        sa.Column('unit', sa.String(length=20), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('comment', sa.Text(), server_default='', nullable=False),
        sa.Column('taken_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['family_id'], ['families.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['medicine_id'], ['medicines.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('intakes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_intakes_family_id'), ['family_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_intakes_medicine_id'), ['medicine_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_intakes_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_intakes_taken_at'), ['taken_at'], unique=False)


def downgrade() -> None:
    op.drop_table('intakes')

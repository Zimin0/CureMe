"""illness_records: история болезней (даты, комментарий, фото документов)

Revision ID: a6c8e0b2d4f1
Revises: f2a4c6e8b0d3
Create Date: 2026-10-09 20:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a6c8e0b2d4f1'
down_revision: Union[str, Sequence[str], None] = 'f2a4c6e8b0d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'illness_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=200), server_default='', nullable=False),
        sa.Column('date_from', sa.Date(), nullable=False),
        sa.Column('date_to', sa.Date(), nullable=False),
        sa.Column('comment', sa.Text(), server_default='', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('illness_records', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_illness_records_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_illness_records_date_from'), ['date_from'], unique=False)
    op.create_table(
        'illness_documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('record_id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['record_id'], ['illness_records.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('illness_documents', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_illness_documents_record_id'), ['record_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('illness_documents', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_illness_documents_record_id'))
    op.drop_table('illness_documents')
    with op.batch_alter_table('illness_records', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_illness_records_date_from'))
        batch_op.drop_index(batch_op.f('ix_illness_records_user_id'))
    op.drop_table('illness_records')

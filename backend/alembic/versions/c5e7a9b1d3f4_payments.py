"""payments: оплаты Плюса через ЮKassa, автопродление на аккаунте

Revision ID: c5e7a9b1d3f4
Revises: b4d8f2a6c0e1
Create Date: 2026-10-03 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c5e7a9b1d3f4'
down_revision: Union[str, Sequence[str], None] = 'b4d8f2a6c0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'payments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('yk_id', sa.String(length=64), nullable=True),
        sa.Column('period', sa.String(length=8), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('recurring', sa.Boolean(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('receipt_url', sa.String(length=500), nullable=True),
        sa.Column('receipt_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_payments_user_id'), 'payments', ['user_id'], unique=False)
    op.create_index(op.f('ix_payments_yk_id'), 'payments', ['yk_id'], unique=True)
    op.add_column('users', sa.Column('auto_renew', sa.Boolean(), server_default='0', nullable=False))
    op.add_column('users', sa.Column('pay_method_id', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('renew_period', sa.String(length=8), nullable=True))
    op.add_column('users', sa.Column('renew_notified_for', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('renew_notified_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for col in ('renew_notified_at', 'renew_notified_for', 'renew_period', 'pay_method_id', 'auto_renew'):
        op.drop_column('users', col)
    op.drop_index(op.f('ix_payments_yk_id'), table_name='payments')
    op.drop_index(op.f('ix_payments_user_id'), table_name='payments')
    op.drop_table('payments')

"""email verification: подтверждение почты письмом

Revision ID: a2d9e4b7c1f3
Revises: f1b8c3d2a4e6
Create Date: 2026-09-29 00:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2d9e4b7c1f3'
down_revision: Union[str, Sequence[str], None] = 'f1b8c3d2a4e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('email_token_hash', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('email_token_sent_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index(batch_op.f('ix_users_email_token_hash'), ['email_token_hash'], unique=True)
    # Тех, кто зарегистрировался до появления проверки, не блокируем: считаем их почту подтверждённой.
    op.execute("UPDATE users SET email_verified_at = created_at")


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_email_token_hash'))
        batch_op.drop_column('email_token_sent_at')
        batch_op.drop_column('email_token_hash')
        batch_op.drop_column('email_verified_at')

"""plan_on_user: тариф Плюс переезжает с семьи на аккаунт главного владельца

Revision ID: d8b4e6a2f1c7
Revises: c9f3a5e7d2b1
Create Date: 2026-09-30 22:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8b4e6a2f1c7'
down_revision: Union[str, Sequence[str], None] = 'c9f3a5e7d2b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('plan', sa.String(length=16), server_default='free', nullable=False))
    op.add_column('users', sa.Column('plus_until', sa.DateTime(timezone=True), nullable=True))

    # Плюс семьи переходит её главному владельцу (самому раннему из владельцев).
    # Если у человека несколько платных семей, берём самый поздний срок; бессрочный (NULL) сильнее любого срока.
    conn = op.get_bind()
    fams = conn.execute(sa.text("SELECT id, plus_until FROM families WHERE plan = 'plus'")).fetchall()
    best: dict[int, tuple[bool, object]] = {}  # user_id -> (бессрочно, срок)
    for fid, until in fams:
        owner = conn.execute(sa.text(
            "SELECT user_id FROM memberships WHERE family_id = :f AND role = 'owner' ORDER BY joined_at, id LIMIT 1"
        ), {"f": fid}).scalar()
        if owner is None:
            continue
        forever, cur = best.get(owner, (False, None))
        if until is None:
            best[owner] = (True, None)
        elif not forever and (cur is None or until > cur):
            best[owner] = (False, until)
    for uid, (forever, until) in best.items():
        conn.execute(
            sa.text("UPDATE users SET plan = 'plus', plus_until = :u WHERE id = :id"),
            {"u": None if forever else until, "id": uid},
        )

    with op.batch_alter_table('families') as batch:
        batch.drop_column('plus_until')
        batch.drop_column('plan')


def downgrade() -> None:
    with op.batch_alter_table('families') as batch:
        batch.add_column(sa.Column('plan', sa.String(length=16), server_default='free', nullable=False))
        batch.add_column(sa.Column('plus_until', sa.DateTime(timezone=True), nullable=True))
    # Плюс аккаунта возвращается всем семьям, где человек главный владелец.
    conn = op.get_bind()
    for uid, until in conn.execute(sa.text("SELECT id, plus_until FROM users WHERE plan = 'plus'")).fetchall():
        for (fid,) in conn.execute(sa.text(
            "SELECT family_id FROM memberships m WHERE m.user_id = :u AND m.role = 'owner' AND m.id = ("
            "SELECT id FROM memberships o WHERE o.family_id = m.family_id AND o.role = 'owner' ORDER BY joined_at, id LIMIT 1)"
        ), {"u": uid}).fetchall():
            conn.execute(sa.text("UPDATE families SET plan = 'plus', plus_until = :t WHERE id = :f"), {"t": until, "f": fid})
    with op.batch_alter_table('users') as batch:
        batch.drop_column('plus_until')
        batch.drop_column('plan')

"""households: семья (household) и аптечки, тариф переезжает с аккаунта на семью

Revision ID: e8a1c3f5b7d9
Revises: c5e7a9b1d3f4
Create Date: 2026-10-03 20:00:00

Таблица families остаётся аптечкой. Каждая связная группа «люди + аптечки» из memberships становится семьёй:
владелец — самый давний из владельцев, остальные участники, Плюс — лучший из тарифов её людей. Человек без аптечек
получает личную семью с пустой аптечкой. Если в группе аптечки с разным составом людей (человек в двух семьях,
у которых есть те, кого нет в другой), миграция останавливается и ничего не меняет: слить их значило бы открыть
людям чужие данные. Перед выкладкой это показывает проверка в админке «Проверить данные».
"""
import secrets
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8a1c3f5b7d9'
down_revision: Union[str, Sequence[str], None] = 'c5e7a9b1d3f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DT = sa.DateTime(timezone=True)
USERS = sa.table(
    'users', sa.column('id', sa.Integer), sa.column('name', sa.String), sa.column('plan', sa.String),
    sa.column('plus_until', DT), sa.column('trial_granted_at', DT), sa.column('household_id', sa.Integer),
    sa.column('household_role', sa.String), sa.column('household_joined_at', DT),
)
FAMILIES = sa.table(
    'families', sa.column('id', sa.Integer), sa.column('name', sa.String), sa.column('invite_code', sa.String),
    sa.column('created_at', DT), sa.column('household_id', sa.Integer), sa.column('created_by_id', sa.Integer),
    sa.column('status', sa.String),
)
MEMBERSHIPS = sa.table(
    'memberships', sa.column('id', sa.Integer), sa.column('family_id', sa.Integer), sa.column('user_id', sa.Integer),
    sa.column('role', sa.String), sa.column('joined_at', DT),
)
PAYMENTS = sa.table('payments', sa.column('user_id', sa.Integer), sa.column('status', sa.String))
HOUSEHOLDS = sa.table(
    'households', sa.column('id', sa.Integer), sa.column('plan', sa.String), sa.column('plus_until', DT),
    sa.column('plus_is_trial', sa.Boolean), sa.column('created_at', DT),
)
TRIAL_MAX_DAYS = 31  # Плюс, который не длиннее этого от даты подарка и без оплат, считаем пробным


def _naive(dt: datetime) -> datetime:
    """SQLite отдаёт время без пояса, Postgres с поясом: для сравнений приводим к одному виду."""
    return dt.replace(tzinfo=None) if dt.tzinfo is None else dt.astimezone(timezone.utc).replace(tzinfo=None)


def _components(memberships) -> list[tuple[set[int], set[int], list]]:
    """Связные группы людей и аптечек: (люди, аптечки, строки memberships)."""
    parent: dict[tuple[str, int], tuple[str, int]] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for m in memberships:
        a, b = find(('u', m.user_id)), find(('f', m.family_id))
        parent[a] = b
    groups: dict[tuple[str, int], list] = defaultdict(list)
    for m in memberships:
        groups[find(('u', m.user_id))].append(m)
    return [({m.user_id for m in rows}, {m.family_id for m in rows}, rows) for rows in groups.values()]


def _best_plus(users) -> tuple[str, datetime | None, object | None]:
    """Лучший тариф людей группы: бессрочный сильнее срока, дальше срок позже. Возвращает (план, срок, человек)."""
    best = None
    for u in users:
        if u.plan != 'plus':
            continue
        key = (u.plus_until is None, _naive(u.plus_until) if u.plus_until else datetime.min)
        if best is None or key > best[0]:
            best = (key, u)
    if best is None:
        return 'free', None, None
    return 'plus', best[1].plus_until, best[1]


def _invite_code(taken: set[str]) -> str:
    alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    while True:
        code = ''.join(secrets.choice(alphabet) for _ in range(8))
        if code not in taken:
            taken.add(code)
            return code


def _read_memberships():
    conn = op.get_bind()
    return list(conn.execute(sa.select(MEMBERSHIPS.c.id, MEMBERSHIPS.c.family_id, MEMBERSHIPS.c.user_id, MEMBERSHIPS.c.role, MEMBERSHIPS.c.joined_at)))


def _check_conflicts() -> None:
    """Первым делом, до любых изменений схемы: если слить группу нельзя, база остаётся как была."""
    groups = _components(_read_memberships())
    conflicts = []
    for uids, fids, group in groups:
        have = defaultdict(set)
        for m in group:
            have[m.family_id].add(m.user_id)
        for fid in fids:
            if have[fid] != uids:
                conflicts.append(f'семья {fid}: люди {sorted(have[fid])}, а в связанных с ней семьях ещё {sorted(uids - have[fid])}')
    if conflicts:
        raise RuntimeError(
            'Миграция семей остановлена, данные не менялись: у людей разные наборы аптечек. Разберите их вручную '
            '(админка, вкладка «Семьи», «Проверить данные»). ' + '; '.join(conflicts[:20])
        )


def _backfill() -> None:
    conn = op.get_bind()
    users = {u.id: u for u in conn.execute(sa.select(USERS.c.id, USERS.c.name, USERS.c.plan, USERS.c.plus_until, USERS.c.trial_granted_at))}
    fams = {f.id: f for f in conn.execute(sa.select(FAMILIES.c.id, FAMILIES.c.name, FAMILIES.c.created_at, FAMILIES.c.invite_code))}
    rows = _read_memberships()
    paid = {r[0] for r in conn.execute(sa.select(PAYMENTS.c.user_id).where(PAYMENTS.c.status == 'succeeded', PAYMENTS.c.user_id.is_not(None)))}
    now = datetime.now(timezone.utc)

    groups = _components(rows)

    taken = {f.invite_code for f in fams.values()}
    for uids, fids, group in groups:
        order = sorted(group, key=lambda m: (_naive(m.joined_at), m.id))
        owners = [m for m in order if m.role == 'owner']
        owner_id = (owners or order)[0].user_id
        plan, until, source = _best_plus([users[i] for i in uids])
        trial = bool(
            source is not None and until is not None and source.trial_granted_at is not None and source.id not in paid
            and _naive(until) <= _naive(source.trial_granted_at) + timedelta(days=TRIAL_MAX_DAYS)
        )
        created = min(_naive(fams[f].created_at) for f in fids)
        hid = conn.execute(HOUSEHOLDS.insert().values(plan=plan, plus_until=until, plus_is_trial=trial, created_at=created).returning(HOUSEHOLDS.c.id)).scalar_one()
        for uid in uids:
            joined = min(m.joined_at for m in group if m.user_id == uid)
            conn.execute(USERS.update().where(USERS.c.id == uid).values(
                household_id=hid, household_role='owner' if uid == owner_id else 'member', household_joined_at=joined))
        for fid in fids:
            first = sorted((m for m in group if m.family_id == fid), key=lambda m: (m.role != 'owner', _naive(m.joined_at), m.id))[0]
            conn.execute(FAMILIES.update().where(FAMILIES.c.id == fid).values(household_id=hid, created_by_id=first.user_id))
        conn.execute(MEMBERSHIPS.update().where(MEMBERSHIPS.c.user_id == owner_id, MEMBERSHIPS.c.family_id.in_(fids)).values(role='owner'))
        conn.execute(MEMBERSHIPS.update().where(MEMBERSHIPS.c.user_id != owner_id, MEMBERSHIPS.c.family_id.in_(fids)).values(role='member'))

    # Человек без аптечек: личная семья и пустая аптечка (R01: нулевой семьи не бывает).
    for uid, u in users.items():
        if any(uid in uids for uids, _, _ in groups):
            continue
        plan, until = ('plus', u.plus_until) if u.plan == 'plus' else ('free', None)
        trial = bool(plan == 'plus' and until is not None and u.trial_granted_at is not None and uid not in paid
                     and _naive(until) <= _naive(u.trial_granted_at) + timedelta(days=TRIAL_MAX_DAYS))
        hid = conn.execute(HOUSEHOLDS.insert().values(plan=plan, plus_until=until, plus_is_trial=trial, created_at=now).returning(HOUSEHOLDS.c.id)).scalar_one()
        conn.execute(USERS.update().where(USERS.c.id == uid).values(household_id=hid, household_role='owner', household_joined_at=now))
        fid = conn.execute(FAMILIES.insert().values(
            name=f'Семья {u.name}', invite_code=_invite_code(taken), created_at=now, household_id=hid, created_by_id=uid, status='active',
        ).returning(FAMILIES.c.id)).scalar_one()
        conn.execute(MEMBERSHIPS.insert().values(family_id=fid, user_id=uid, role='owner', joined_at=now))


def upgrade() -> None:
    _check_conflicts()
    op.create_table(
        'households',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('plan', sa.String(length=16), server_default='free', nullable=False),
        sa.Column('plus_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('plus_is_trial', sa.Boolean(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'household_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('household_id', sa.Integer(), nullable=True),
        sa.Column('kind', sa.String(length=32), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('actor_id', sa.Integer(), nullable=True),
        sa.Column('detail', sa.Text(), server_default='', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['household_id'], ['households.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_household_events_household_id'), 'household_events', ['household_id'], unique=False)
    op.create_index(op.f('ix_household_events_created_at'), 'household_events', ['created_at'], unique=False)

    with op.batch_alter_table('users') as batch:
        batch.add_column(sa.Column('household_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('household_role', sa.String(length=16), server_default='member', nullable=False))
        batch.add_column(sa.Column('household_joined_at', sa.DateTime(timezone=True), server_default=sa.text("'2026-01-01 00:00:00'"), nullable=False))
        batch.create_foreign_key('fk_users_household_id', 'households', ['household_id'], ['id'], ondelete='SET NULL')
        batch.create_index(op.f('ix_users_household_id'), ['household_id'], unique=False)
    with op.batch_alter_table('families') as batch:
        batch.add_column(sa.Column('household_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('created_by_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('status', sa.String(length=16), server_default='active', nullable=False))
        batch.create_foreign_key('fk_families_household_id', 'households', ['household_id'], ['id'], ondelete='CASCADE')
        batch.create_foreign_key('fk_families_created_by_id', 'users', ['created_by_id'], ['id'], ondelete='SET NULL')
        batch.create_index(op.f('ix_families_household_id'), ['household_id'], unique=False)

    _backfill()


def downgrade() -> None:
    # Плюс семьи возвращается её владельцу (как было на аккаунте). Колонки plan и plus_until у users остались.
    conn = op.get_bind()
    for hid, plan, until in conn.execute(sa.select(HOUSEHOLDS.c.id, HOUSEHOLDS.c.plan, HOUSEHOLDS.c.plus_until)).fetchall():
        if plan == 'plus':
            conn.execute(USERS.update().where(USERS.c.household_id == hid, USERS.c.household_role == 'owner').values(plan='plus', plus_until=until))
    with op.batch_alter_table('families') as batch:
        batch.drop_index(op.f('ix_families_household_id'))
        batch.drop_constraint('fk_families_created_by_id', type_='foreignkey')
        batch.drop_constraint('fk_families_household_id', type_='foreignkey')
        batch.drop_column('status')
        batch.drop_column('created_by_id')
        batch.drop_column('household_id')
    with op.batch_alter_table('users') as batch:
        batch.drop_index(op.f('ix_users_household_id'))
        batch.drop_constraint('fk_users_household_id', type_='foreignkey')
        batch.drop_column('household_joined_at')
        batch.drop_column('household_role')
        batch.drop_column('household_id')
    op.drop_index(op.f('ix_household_events_created_at'), table_name='household_events')
    op.drop_index(op.f('ix_household_events_household_id'), table_name='household_events')
    op.drop_table('household_events')
    op.drop_table('households')

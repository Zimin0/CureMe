"""Проверка данных перед переходом на модель «семья + аптечки» (docs/household-model). Только чтение.

Сейчас таблица `families` это аптечка со своим списком людей. В новой модели у человека ровно одна семья,
и все её члены видят все её аптечки. Поэтому безопасно склеить в одну семью только такую группу людей
и аптечек, где каждый человек состоит в каждой аптечке группы. Здесь мы находим такие группы и показываем,
где склеивание дало бы кому-то лишний доступ, чтобы разобрать эти случаи до миграции.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Family, Membership, User
from .plans import family_owner_user, plus_active

FREE_MEMBERS = 3  # людей в бесплатной семье по новым правилам (R02)


def _components(db: Session) -> list[tuple[set[int], set[int]]]:
    """Группы (люди, аптечки): люди связаны, если состоят в одной аптечке. Аптечка без людей остаётся группой сама."""
    parent: dict[tuple[str, int], tuple[str, int]] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for fid in db.scalars(select(Family.id)):
        find(("f", fid))
    for uid in db.scalars(select(User.id)):
        find(("u", uid))
    for m in db.scalars(select(Membership)):
        parent[find(("u", m.user_id))] = find(("f", m.family_id))
    groups: dict[tuple[str, int], tuple[set[int], set[int]]] = {}
    for key in list(parent):
        users, fams = groups.setdefault(find(key), (set(), set()))
        (users if key[0] == "u" else fams).add(key[1])
    return list(groups.values())


def analyze(db: Session) -> dict:
    users = {u.id: u for u in db.scalars(select(User))}
    fams = {f.id: f for f in db.scalars(select(Family))}
    pairs = {(m.user_id, m.family_id) for m in db.scalars(select(Membership))}

    households, conflicts, over_limits = [], [], []
    for uids, fids in _components(db):
        missing = sorted((u, f) for u in uids for f in fids if (u, f) not in pairs)
        item = {
            "users": [f"{users[u].name} <{users[u].email}>" for u in sorted(uids)],
            "families": [fams[f].name for f in sorted(fids)],
            "complete": not missing,
        }
        households.append(item)
        if missing:
            item["missing"] = [f"{users[u].email} не состоит в «{fams[f].name}»" for u, f in missing]
            conflicts.append(item)
        owners = [family_owner_user(fams[f]) for f in fids]
        has_plus = any(o is not None and plus_active(o) for o in owners)
        if not has_plus and (len(uids) > FREE_MEMBERS or len(fids) > max(len(uids), 1)):
            over_limits.append(item)

    multi_owner = [
        {"family": f.name, "owners": [m.user.email for m in sorted(f.memberships, key=lambda m: m.joined_at) if m.role == "owner"]}
        for f in fams.values() if sum(1 for m in f.memberships if m.role == "owner") > 1
    ]
    no_owner = [f.name for f in fams.values() if f.memberships and not any(m.role == "owner" for m in f.memberships)]
    return {
        "users": len(users), "families": len(fams), "would_create_households": len(households),
        "users_without_family": [u.email for u in users.values() if not u.memberships],
        "families_without_people": [f.name for f in fams.values() if not f.memberships],
        "households": households,
        "conflicts": conflicts,
        "multi_owner_families": multi_owner,
        "families_without_owner": no_owner,
        "over_free_limits": over_limits,
        "safe": not conflicts and not no_owner,
    }

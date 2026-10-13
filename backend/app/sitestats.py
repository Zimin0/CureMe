"""Собственная статистика сайта: заходы и нажатия считаются на нашем сервере, в базе, без сторонних сервисов.

Не храним cookie, IP, User-Agent, идентификатор посетителя и адреса с кодами: только «за день столько-то заходов
на такую страницу, с такого источника». Регистрации, подтверждения, лекарства и оплаты считаются прямо из таблиц.
"""

import re
from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Medicine, Payment, SiteStat, User

# Публичные страницы: всё остальное записываем как /app (внутри аккаунта адреса несут номера и коды).
PUBLIC_PAGES = {"", "login", "register", "plus", "privacy", "terms", "consent", "offer", "consent-share",
                "consent-telegram", "consent-trusted", "reset-password", "join"}
GOALS = {"plus_view", "pay_click"}  # остальные цели считаются из базы
MAX_KEYS_PER_DAY = 300  # чужой вброс случайных источников не раздует таблицу


def safe_path(path: str) -> str:
    first = (path or "").split("?")[0].split("#")[0].split("/")[1:2]
    first = first[0] if first else ""
    return f"/{first}" if first in PUBLIC_PAGES else "/app"


def referrer_host(ref: str | None, own_host: str | None = None) -> str:
    """Только домен источника (yandex.ru, t.me); свои страницы и мусор — пустая строка."""
    if not ref:
        return ""
    host = (urlparse(ref).hostname or "").lower().removeprefix("www.")
    if not re.fullmatch(r"[a-z0-9.-]{3,60}", host) or host == (own_host or "").lower().removeprefix("www."):
        return ""
    return host


def clean_utm(value: str | None) -> str:
    v = (value or "").strip().lower()
    return v if re.fullmatch(r"[a-z0-9_.-]{1,40}", v) else ""


def bump(db: Session, kind: str, key: str, day: date | None = None) -> None:
    day = day or datetime.now(timezone.utc).date()
    row = db.get(SiteStat, (day, kind, key))
    if row is None:
        keys = db.scalar(select(func.count()).select_from(SiteStat).where(SiteStat.day == day, SiteStat.kind == kind)) or 0
        if keys >= MAX_KEYS_PER_DAY:
            key = "other"
            row = db.get(SiteStat, (day, kind, key))
        if row is None:
            row = SiteStat(day=day, kind=kind, key=key, count=0)
            db.add(row)
    row.count = (row.count or 0) + 1
    db.commit()


def report(db: Session, days: int = 30) -> dict:
    today = datetime.now(timezone.utc).date()
    since = today - timedelta(days=days - 1)
    start = datetime.combine(since, time.min, tzinfo=timezone.utc)

    per_day = lambda rows: {d: n for d, n in rows}  # noqa: E731  (func.date отдаёт date на Postgres и строку на SQLite)

    day_of = lambda col: func.date(col)  # noqa: E731
    counts = {}
    counts["registrations"] = per_day(db.execute(select(day_of(User.created_at), func.count()).where(User.created_at >= start).group_by(day_of(User.created_at))))
    counts["verified"] = per_day(db.execute(select(day_of(User.email_verified_at), func.count()).where(User.email_verified_at >= start).group_by(day_of(User.email_verified_at))))
    counts["medicines"] = per_day(db.execute(select(day_of(Medicine.created_at), func.count()).where(Medicine.created_at >= start).group_by(day_of(Medicine.created_at))))
    counts["paid"] = per_day(db.execute(select(day_of(Payment.paid_at), func.count()).where(Payment.status == "succeeded", Payment.paid_at >= start).group_by(day_of(Payment.paid_at))))
    stats = db.execute(select(SiteStat).where(SiteStat.day >= since)).scalars().all()
    by = lambda kind: [s for s in stats if s.kind == kind]  # noqa: E731
    for name, kind in (("visits", "visit"),):
        counts[name] = {s.day: s.count for s in by(kind)}
    for g in GOALS:
        counts[g] = {s.day: s.count for s in by("goal") if s.key == g}

    def norm(m: dict) -> dict:
        return {(k if isinstance(k, date) else date.fromisoformat(str(k))): v for k, v in m.items()}

    counts = {k: norm(v) for k, v in counts.items()}
    cols = ["visits", "registrations", "verified", "medicines", "plus_view", "pay_click", "paid"]
    rows = []
    for i in range(days):
        d = today - timedelta(days=i)
        rows.append({"day": d.isoformat(), **{c: counts[c].get(d, 0) for c in cols}})
    totals = {c: sum(r[c] for r in rows) for c in cols}

    def top(kind: str) -> list[dict]:
        agg: dict[str, int] = {}
        for s in by(kind):
            agg[s.key or "(напрямую)"] = agg.get(s.key or "(напрямую)", 0) + s.count
        return [{"key": k, "count": v} for k, v in sorted(agg.items(), key=lambda kv: -kv[1])[:15]]

    return {"days": days, "rows": rows, "totals": totals, "sources": top("ref"), "utm": top("utm"), "pages": top("page")}

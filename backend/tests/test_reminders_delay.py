from datetime import date, datetime, timedelta, timezone

from app import reminders
from app.reminders import NEW_PACKAGE_DELAY, _is_fresh


class P:
    def __init__(self, added_at):
        self.added_at = added_at


def test_fresh_package_window():
    now = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)
    assert _is_fresh(P(now - timedelta(hours=11, minutes=59)), now)
    assert not _is_fresh(P(now - NEW_PACKAGE_DELAY), now)
    assert not _is_fresh(P(now - timedelta(days=3)), now)


def test_naive_added_at_treated_as_utc():
    now = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)
    assert _is_fresh(P(datetime(2026, 9, 30, 6)), now)

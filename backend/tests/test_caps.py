"""
Quiet-hours and weekend-damping detection.

The scheduler already enforces both; these tests cover the read-side helpers
that let the account/run-status view say "quiet hours -- this is expected, not
a bug" instead of a support ticket getting filed against a scheduler that is
behaving exactly as designed.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.accounts import caps as caps_policy


class _Account:
    def __init__(self, daily_caps: dict):
        self.daily_caps = daily_caps


def test_quiet_hours_uses_the_accounts_own_timezone():
    account = _Account({"active_hours": [8, 19], "timezone": "America/New_York"})

    # 2am UTC is 9pm the previous day in New York -- outside 8-19.
    assert caps_policy.in_quiet_hours(account, now=datetime(2026, 9, 9, 2, 0, tzinfo=timezone.utc))
    # 2pm UTC is 10am in New York -- inside 8-19.
    assert not caps_policy.in_quiet_hours(
        account, now=datetime(2026, 9, 9, 14, 0, tzinfo=timezone.utc)
    )


def test_quiet_hours_falls_back_to_utc_with_no_timezone_set():
    account = _Account({"active_hours": [8, 19]})

    assert not caps_policy.in_quiet_hours(
        account, now=datetime(2026, 9, 9, 14, 0, tzinfo=timezone.utc)
    )
    assert caps_policy.in_quiet_hours(account, now=datetime(2026, 9, 9, 22, 0, tzinfo=timezone.utc))


def test_weekend_is_detected_in_the_accounts_timezone():
    account = _Account({"timezone": "America/New_York"})

    saturday = datetime(2026, 9, 12, 14, 0, tzinfo=timezone.utc)
    wednesday = datetime(2026, 9, 9, 14, 0, tzinfo=timezone.utc)
    assert caps_policy.is_weekend(account, now=saturday)
    assert not caps_policy.is_weekend(account, now=wednesday)


def test_an_unknown_timezone_name_does_not_crash_the_status_check():
    account = _Account({"active_hours": [8, 19], "timezone": "Not/ARealZone"})

    # Falls back to reading the window in UTC rather than raising -- a typo'd
    # tz name must never be the reason the run-status view goes blank.
    assert caps_policy.in_quiet_hours(account, now=datetime(2026, 9, 9, 22, 0, tzinfo=timezone.utc))


def test_describe_surfaces_quiet_hours_and_weekend_for_the_ui():
    account = _Account({"active_hours": [8, 19], "timezone": "America/New_York"})

    snapshot = caps_policy.describe(account)
    assert "quiet_hours_now" in snapshot
    assert "weekend_now" in snapshot

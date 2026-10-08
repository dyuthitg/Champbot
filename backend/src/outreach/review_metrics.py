"""
Review-queue metrics: how the human side of the loop is going.

Four numbers, all over items a person actually decided in the window:

    items            how many were reviewed (approved + rejected)
    approval rate    approved / reviewed
    edits per item   approvals whose sent text differs from the draft / approvals
    time to approve  created_at -> reviewed_at, median and 90th percentile

Auto-approved comments (the step-down rule, src/outreach/stepdown.py) are
counted separately and kept out of all four. Nobody looked at them, so folding
them in would push the approval rate towards 100% and the time to approve
towards zero exactly as the account earns trust -- the metric would be
measuring the rule, not the reviewers.

An approval only ever carries one edit (the text is fixed once it's approved),
so "edits per item" is also the share of approvals that were edited. It is the
clearest single read on draft quality: every edit is a draft someone had to
fix before it was fit to send.

Computed in Python over one row per decision rather than in SQL: a window is a
few hundred rows at most, percentiles aren't portable across SQLite and
Postgres, and the same code then serves the tests and production.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from statistics import median
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.outreach.models import OutreachSuggestion, SuggestionStatus


def _utc(value: datetime) -> datetime:
    # SQLite hands timezone-aware columns back naive; they were written as UTC.
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _was_edited(draft: Optional[str], final: Optional[str]) -> bool:
    # Whitespace-only differences are the textarea, not the reviewer.
    return (final or "").strip() != (draft or "").strip()


def _percentile(values: list[float], pct: float) -> Optional[float]:
    """Nearest-rank percentile; None for an empty list."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, -(-len(ordered) * pct // 100))  # ceil without importing math
    return ordered[int(rank) - 1]


def _bucket() -> dict:
    return {"reviewed": 0, "approved": 0, "rejected": 0, "edited": 0, "_waits": []}


def _finish(bucket: dict) -> dict:
    waits = bucket.pop("_waits")
    reviewed, approved = bucket["reviewed"], bucket["approved"]
    bucket["approval_rate"] = round(100 * approved / reviewed, 1) if reviewed else None
    bucket["edits_per_item"] = round(bucket["edited"] / approved, 2) if approved else None
    bucket["median_seconds_to_approve"] = round(median(waits)) if waits else None
    p90 = _percentile(waits, 90)
    bucket["p90_seconds_to_approve"] = round(p90) if p90 is not None else None
    return bucket


async def compute(
    db: AsyncSession,
    org_id: str,
    *,
    days: int = 7,
    account_id: Optional[str] = None,
    now: Optional[datetime] = None,
) -> dict:
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)

    scope = [OutreachSuggestion.org_id == uuid.UUID(str(org_id))]
    if account_id:
        scope.append(OutreachSuggestion.account_id == uuid.UUID(str(account_id)))

    rows = (
        await db.execute(
            select(
                OutreachSuggestion.action,
                OutreachSuggestion.status,
                OutreachSuggestion.draft_text,
                OutreachSuggestion.final_text,
                OutreachSuggestion.created_at,
                OutreachSuggestion.reviewed_at,
                OutreachSuggestion.result,
            ).where(
                *scope,
                OutreachSuggestion.reviewed_at.is_not(None),
                OutreachSuggestion.reviewed_at >= since,
            )
        )
    ).all()

    totals = _bucket()
    by_action: dict[str, dict] = defaultdict(_bucket)
    by_day: dict[date, dict] = {}
    auto_approved = 0

    for row in rows:
        if (row.result or {}).get("auto_approved"):
            auto_approved += 1
            continue
        reviewed_at = _utc(row.reviewed_at)
        day = reviewed_at.date()
        buckets = [totals, by_action[row.action], by_day.setdefault(day, _bucket())]

        approved = row.status != SuggestionStatus.REJECTED
        edited = approved and _was_edited(row.draft_text, row.final_text)
        wait = (reviewed_at - _utc(row.created_at)).total_seconds() if approved else None

        for b in buckets:
            b["reviewed"] += 1
            if approved:
                b["approved"] += 1
                b["_waits"].append(max(0.0, wait))
                if edited:
                    b["edited"] += 1
            else:
                b["rejected"] += 1

    # What's waiting right now -- the other half of "how is the queue doing".
    pending_count, oldest_pending = (
        await db.execute(
            select(func.count(), func.min(OutreachSuggestion.created_at)).where(
                *scope, OutreachSuggestion.status == SuggestionStatus.PENDING
            )
        )
    ).one()

    # One entry per calendar day in the window, zero days included, so a
    # chart of it never silently skips the days nobody reviewed anything.
    first_day = since.date()
    daily = []
    for offset in range((now.date() - first_day).days + 1):
        day = first_day + timedelta(days=offset)
        daily.append({"date": day.isoformat(), **_finish(by_day.get(day) or _bucket())})

    return {
        "days": days,
        "since": since,
        "until": now,
        "totals": _finish(totals),
        "auto_approved": auto_approved,
        "pending_now": int(pending_count or 0),
        "oldest_pending_seconds": (
            round((now - _utc(oldest_pending)).total_seconds()) if oldest_pending else None
        ),
        "by_action": [
            {"action": action, **_finish(bucket)}
            for action, bucket in sorted(by_action.items(), key=lambda kv: -kv[1]["reviewed"])
        ],
        "daily": daily,
    }

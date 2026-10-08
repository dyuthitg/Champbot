"""
Review-queue metrics: items, approval rate, edits per item, time to approve.

Rows are written with explicit timestamps so the arithmetic is checkable by
hand; one test goes through the real approve/reject calls to prove the
fields the metrics read are the ones those calls actually write.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from src.api.middleware.clerk import RequestContext
from src.api.routes.outreach import review_metrics_view
from src.outreach import execute as executor
from src.outreach import review_metrics
from src.outreach.models import OutreachSuggestion, SuggestionStatus
from src.targeting.models import OutreachTarget

NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
DRAFT = (
    "Cutting the signup form from nine fields to two is a bold call, Ada. "
    "What convinced you the other seven were not buying anything?"
)


async def _add(
    db,
    org,
    account,
    *,
    status=SuggestionStatus.SCHEDULED,
    action="comment",
    created=None,
    reviewed=None,
    final=DRAFT,
    result=None,
):
    organization, _ = org
    target = OutreachTarget(
        id=uuid.uuid4(),
        org_id=organization.id,
        account_id=account.id,
        member_urn=f"urn:li:fs_profile:{uuid.uuid4().hex[:8]}",
        full_name="Ada Lovelace",
        first_name="Ada",
        title="Head of Growth",
        company="Northwind",
    )
    db.add(target)
    row = OutreachSuggestion(
        id=uuid.uuid4(),
        org_id=organization.id,
        account_id=account.id,
        target_id=target.id,
        action=action,
        status=status,
        draft_text=DRAFT,
        final_text=final if status != SuggestionStatus.PENDING else None,
        created_at=created,
        reviewed_at=reviewed,
        result=result,
    )
    db.add(row)
    await db.commit()
    return row


async def test_the_four_numbers(db, org, account):
    day = NOW - timedelta(days=1)
    # Three approvals, one edited, waiting 10, 20 and 60 minutes.
    await _add(db, org, account, created=day, reviewed=day + timedelta(minutes=10))
    await _add(db, org, account, created=day, reviewed=day + timedelta(minutes=20))
    await _add(
        db, org, account, created=day, reviewed=day + timedelta(minutes=60),
        final=DRAFT.replace("bold call", "brave call"),
    )
    # One rejection.
    await _add(
        db, org, account, status=SuggestionStatus.REJECTED,
        created=day, reviewed=day + timedelta(minutes=5), final=None,
    )

    data = await review_metrics.compute(db, org[0].id, days=7, now=NOW)
    t = data["totals"]
    assert (t["reviewed"], t["approved"], t["rejected"], t["edited"]) == (4, 3, 1, 1)
    assert t["approval_rate"] == 75.0
    assert t["edits_per_item"] == 0.33
    # Rejections don't have a time to approve.
    assert t["median_seconds_to_approve"] == 20 * 60
    assert t["p90_seconds_to_approve"] == 60 * 60


async def test_whitespace_is_not_an_edit(db, org, account):
    day = NOW - timedelta(hours=3)
    await _add(db, org, account, created=day, reviewed=day, final=f"  {DRAFT}\n")

    data = await review_metrics.compute(db, org[0].id, now=NOW)
    assert data["totals"]["edited"] == 0
    assert data["totals"]["edits_per_item"] == 0.0


async def test_auto_approvals_stay_out_of_the_rates(db, org, account):
    """Nobody looked at these; counting them would measure the rule, not the people."""
    day = NOW - timedelta(days=1)
    await _add(
        db, org, account, status=SuggestionStatus.REJECTED,
        created=day, reviewed=day, final=None,
    )
    for _ in range(5):
        await _add(
            db, org, account, created=day, reviewed=day,
            result={"auto_approved": True, "approval_stage": 2},
        )

    data = await review_metrics.compute(db, org[0].id, now=NOW)
    assert data["auto_approved"] == 5
    assert data["totals"]["reviewed"] == 1
    assert data["totals"]["approval_rate"] == 0.0


async def test_window_and_empty_days(db, org, account):
    old = NOW - timedelta(days=10)
    await _add(db, org, account, created=old, reviewed=old)  # outside 7 days
    recent = NOW - timedelta(days=2)
    await _add(db, org, account, created=recent, reviewed=recent)

    data = await review_metrics.compute(db, org[0].id, days=7, now=NOW)
    assert data["totals"]["reviewed"] == 1
    # Every calendar day is present, including the quiet ones.
    assert len(data["daily"]) == 8
    assert sum(d["reviewed"] for d in data["daily"]) == 1
    quiet = [d for d in data["daily"] if d["reviewed"] == 0]
    assert all(d["approval_rate"] is None for d in quiet)


async def test_nothing_reviewed_reads_as_no_data_not_zero(db, org, account):
    data = await review_metrics.compute(db, org[0].id, now=NOW)
    t = data["totals"]
    assert t["reviewed"] == 0
    assert t["approval_rate"] is None
    assert t["edits_per_item"] is None
    assert t["median_seconds_to_approve"] is None


async def test_pending_now_and_oldest(db, org, account):
    await _add(db, org, account, status=SuggestionStatus.PENDING, created=NOW - timedelta(hours=5))
    await _add(db, org, account, status=SuggestionStatus.PENDING, created=NOW - timedelta(hours=1))

    data = await review_metrics.compute(db, org[0].id, now=NOW)
    assert data["pending_now"] == 2
    assert data["oldest_pending_seconds"] == 5 * 3600


async def test_by_action_split(db, org, account):
    day = NOW - timedelta(days=1)
    await _add(db, org, account, action="comment", created=day, reviewed=day)
    await _add(db, org, account, action="comment", created=day, reviewed=day)
    await _add(
        db, org, account, action="connect", status=SuggestionStatus.REJECTED,
        created=day, reviewed=day, final=None,
    )

    data = await review_metrics.compute(db, org[0].id, now=NOW)
    split = {b["action"]: b for b in data["by_action"]}
    assert split["comment"]["approval_rate"] == 100.0
    assert split["connect"]["approval_rate"] == 0.0
    assert data["by_action"][0]["action"] == "comment"  # busiest first


async def test_through_the_real_approve_and_reject(db, org, warm_account):
    """The metrics read what approve()/reject() write -- not a guess at it."""
    plain = await _add(db, org, warm_account, status=SuggestionStatus.PENDING)
    edited = await _add(db, org, warm_account, status=SuggestionStatus.PENDING)
    rejected = await _add(db, org, warm_account, status=SuggestionStatus.PENDING)

    await executor.approve(db, plain)
    await executor.approve(db, edited, edited_text=DRAFT.replace("bold call", "brave call"))
    await executor.reject(db, rejected, reason="wrong post")

    organization, user = org
    ctx = RequestContext(
        user_id=str(user.id),
        org_id=str(organization.id),
        clerk_user_id="metrics-test",
        clerk_org_id=None,
        email="metrics@example.com",
        role="owner",
    )
    response = await review_metrics_view(days=7, account_id=str(warm_account.id), ctx=ctx, db=db)
    t = response.totals
    assert (t.reviewed, t.approved, t.rejected, t.edited) == (3, 2, 1, 1)
    assert t.edits_per_item == 0.5
    assert t.median_seconds_to_approve is not None

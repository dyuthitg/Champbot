"""
The step-down rule (src/outreach/stepdown.py), as agreed with Champ on
2026-10-07: 100% -> 50% -> 20% after 5 clean batches each, and straight back
to 100% on any trigger.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from src.outreach import execute as executor
from src.outreach import health as health_module
from src.outreach import stepdown
from src.outreach.models import OutreachSuggestion, SuggestionAction, SuggestionStatus
from src.targeting.models import OutreachTarget

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
HEALTHY = SimpleNamespace(verdict=health_module.HEALTHY, headline="ok")


async def _target(db, account):
    target = OutreachTarget(
        id=uuid.uuid4(),
        org_id=account.org_id,
        account_id=account.id,
        member_urn=f"urn:li:fs_profile:{uuid.uuid4().hex[:10]}",
        full_name="Dana Whitfield",
        context={"post_urn": "urn:li:activity:1", "post_text": "We raised a seed round."},
    )
    db.add(target)
    await db.flush()
    return target


async def _comment(db, account, *, status, created_at, warnings=None, result=None):
    target = await _target(db, account)
    row = OutreachSuggestion(
        id=uuid.uuid4(),
        org_id=account.org_id,
        account_id=account.id,
        target_id=target.id,
        action=SuggestionAction.COMMENT,
        status=status,
        draft_text="Congrats on the seed round -- 18 months of runway is a real choice.",
        quality_warnings=warnings or [],
        generated_by="openrouter:test-model",
        created_at=created_at,
        result=result,
    )
    db.add(row)
    await db.flush()
    return row


async def _clean_days(db, account, days, per_day=10, start_days_ago=None):
    """`days` finished days of `per_day` sent comments, ending yesterday."""
    start = start_days_ago or days
    for offset in range(start, start - days, -1):
        day = NOW - timedelta(days=offset)
        for _ in range(per_day):
            await _comment(db, account, status=SuggestionStatus.SENT, created_at=day)
    await db.commit()


def _set_stage(account, stage):
    current = stepdown.state(account)
    current["stage"] = stage
    stepdown._save(account, current)


# ----------------------------------------------------------------------
# Stepping down
# ----------------------------------------------------------------------


async def test_a_new_account_checks_every_comment(account):
    assert stepdown.summary(account)["check_percent"] == 100


async def test_five_clean_batches_step_down_to_50_then_five_more_to_20(db, account):
    await _clean_days(db, account, 5, start_days_ago=10)
    summary = await stepdown.evaluate(db, account, health_report=HEALTHY, now=NOW - timedelta(days=5))
    assert summary["check_percent"] == 50
    assert summary["clean_streak"] == 0

    await _clean_days(db, account, 5)
    summary = await stepdown.evaluate(db, account, health_report=HEALTHY, now=NOW)
    assert summary["check_percent"] == 20

    # 20% is the floor: more clean days never go lower.
    summary = await stepdown.evaluate(db, account, health_report=HEALTHY, now=NOW + timedelta(days=10))
    assert summary["check_percent"] == 20


async def test_four_clean_batches_are_not_enough(db, account):
    await _clean_days(db, account, 4)
    summary = await stepdown.evaluate(db, account, health_report=HEALTHY, now=NOW)
    assert summary["check_percent"] == 100
    assert summary["clean_streak"] == 4


async def test_a_day_with_fewer_than_10_comments_does_not_count(db, account):
    await _clean_days(db, account, 5, per_day=9)
    summary = await stepdown.evaluate(db, account, health_report=HEALTHY, now=NOW)
    assert summary["clean_streak"] == 0
    assert summary["check_percent"] == 100


async def test_today_is_never_judged_before_it_ends(db, account):
    for _ in range(10):
        await _comment(db, account, status=SuggestionStatus.SENT, created_at=NOW)
    await db.commit()
    summary = await stepdown.evaluate(db, account, health_report=HEALTHY, now=NOW)
    assert summary["clean_streak"] == 0


async def test_a_day_still_waiting_for_review_stops_the_count(db, account):
    await _clean_days(db, account, 3, start_days_ago=5)
    # Day 2 ago still has a comment nobody has looked at.
    day = NOW - timedelta(days=2)
    for _ in range(10):
        await _comment(db, account, status=SuggestionStatus.SENT, created_at=day)
    await _comment(db, account, status=SuggestionStatus.PENDING, created_at=day)
    await db.commit()

    summary = await stepdown.evaluate(db, account, health_report=HEALTHY, now=NOW)
    assert summary["clean_streak"] == 3


async def test_days_are_not_counted_twice(db, account):
    await _clean_days(db, account, 3)
    await stepdown.evaluate(db, account, health_report=HEALTHY, now=NOW)
    summary = await stepdown.evaluate(db, account, health_report=HEALTHY, now=NOW)
    assert summary["clean_streak"] == 3


# ----------------------------------------------------------------------
# Sampling
# ----------------------------------------------------------------------


async def test_sampling_follows_the_stage(db, account):
    row = await _comment(db, account, status=SuggestionStatus.PENDING, created_at=NOW)
    assert stepdown.needs_review(account, row, rng=lambda: 0.99) == (True, "stage_1")

    _set_stage(account, 2)
    assert stepdown.needs_review(account, row, rng=lambda: 0.49)[0] is True
    assert stepdown.needs_review(account, row, rng=lambda: 0.51)[0] is False

    _set_stage(account, 3)
    assert stepdown.needs_review(account, row, rng=lambda: 0.19)[0] is True
    assert stepdown.needs_review(account, row, rng=lambda: 0.21)[0] is False


async def test_invitations_and_messages_are_always_checked(db, account):
    _set_stage(account, 3)
    row = SimpleNamespace(action=SuggestionAction.CONNECT, quality_warnings=[])
    assert stepdown.needs_review(account, row, rng=lambda: 0.99)[0] is True


async def test_an_unpicked_comment_is_approved_and_marked(db, warm_account):
    account = warm_account
    _set_stage(account, 3)
    stepdown._save(account, {**stepdown.state(account), "copy_fingerprint": stepdown.copy_fingerprint("openrouter:test-model")})
    row = await _comment(db, account, status=SuggestionStatus.PENDING, created_at=NOW)
    await db.commit()

    counts = await stepdown.apply_to_new(db, account, [row], rng=lambda: 0.99)
    await db.refresh(row)

    assert counts == {"checked": 0, "auto_approved": 1}
    assert row.status == SuggestionStatus.SCHEDULED
    assert row.result == {"auto_approved": True, "approval_stage": 3}
    assert row.reviewed_by is None


async def test_a_picked_comment_stays_in_the_queue(db, warm_account):
    account = warm_account
    _set_stage(account, 3)
    stepdown._save(account, {**stepdown.state(account), "copy_fingerprint": stepdown.copy_fingerprint("openrouter:test-model")})
    row = await _comment(db, account, status=SuggestionStatus.PENDING, created_at=NOW)
    await db.commit()

    counts = await stepdown.apply_to_new(db, account, [row], rng=lambda: 0.05)
    await db.refresh(row)
    assert counts == {"checked": 1, "auto_approved": 0}
    assert row.status == SuggestionStatus.PENDING


# ----------------------------------------------------------------------
# Going back to 100%
# ----------------------------------------------------------------------


async def _at_stage_3_with_unsent_auto_approval(db, account):
    _set_stage(account, 3)
    current = stepdown.state(account)
    current["clean_streak"] = 2
    current["copy_fingerprint"] = stepdown.copy_fingerprint("openrouter:test-model")
    stepdown._save(account, current)
    waved = await _comment(
        db, account, status=SuggestionStatus.SCHEDULED, created_at=NOW,
        result={"auto_approved": True, "approval_stage": 3},
    )
    hand = await _comment(db, account, status=SuggestionStatus.SCHEDULED, created_at=NOW)
    await db.commit()
    return waved, hand


async def test_a_problem_reject_resets_and_pulls_unchecked_comments_back(db, account):
    waved, hand = await _at_stage_3_with_unsent_auto_approval(db, account)
    victim = await _comment(db, account, status=SuggestionStatus.PENDING, created_at=NOW)
    await db.commit()

    await executor.reject(db, victim, reason="made up a funding number", comment_problem=True, account=account)
    await db.refresh(waved)
    await db.refresh(hand)

    summary = stepdown.summary(account)
    assert summary["check_percent"] == 100
    assert summary["clean_streak"] == 0
    assert "made up a funding number" in summary["last_reset_reason"]
    assert waved.status == SuggestionStatus.PENDING  # back for a human to check
    assert hand.status == SuggestionStatus.SCHEDULED  # a person already approved it


async def test_tone_prefix_counts_as_a_problem_reject(db, account):
    await _at_stage_3_with_unsent_auto_approval(db, account)
    victim = await _comment(db, account, status=SuggestionStatus.PENDING, created_at=NOW)
    await db.commit()
    await executor.reject(db, victim, reason="Tone: too salesy", account=account)
    assert stepdown.summary(account)["check_percent"] == 100


async def test_a_poor_fit_reject_does_not_reset(db, account):
    await _at_stage_3_with_unsent_auto_approval(db, account)
    victim = await _comment(db, account, status=SuggestionStatus.PENDING, created_at=NOW)
    await db.commit()
    await executor.reject(db, victim, reason="post is about a bereavement, skip", account=account)
    assert stepdown.summary(account)["check_percent"] == 20


async def test_a_problem_reject_makes_its_day_unclean(db, account):
    day = NOW - timedelta(days=1)
    for _ in range(10):
        await _comment(db, account, status=SuggestionStatus.SENT, created_at=day)
    bad = await _comment(db, account, status=SuggestionStatus.PENDING, created_at=day)
    await db.commit()
    await executor.reject(db, bad, reason="Safety: mentions their illness", account=account)

    # Reset marks today as the restart point, so judge from a fresh state.
    current = stepdown.state(account)
    current["last_day_counted"] = None
    stepdown._save(account, current)
    summary = await stepdown.evaluate(db, account, health_report=HEALTHY, now=NOW)
    assert summary["clean_streak"] == 0


async def test_a_flagged_comment_that_would_skip_review_resets(db, warm_account):
    account = warm_account
    _set_stage(account, 2)
    stepdown._save(account, {**stepdown.state(account), "copy_fingerprint": stepdown.copy_fingerprint("openrouter:test-model")})
    row = await _comment(
        db, account, status=SuggestionStatus.PENDING, created_at=NOW,
        warnings=["Uses an exclamation mark"],
    )
    await db.commit()

    counts = await stepdown.apply_to_new(db, account, [row], rng=lambda: 0.99)
    assert counts["auto_approved"] == 0
    assert stepdown.summary(account)["check_percent"] == 100
    await db.refresh(row)
    assert row.status == SuggestionStatus.PENDING


async def test_bad_account_health_resets(db, account):
    _set_stage(account, 3)
    danger = SimpleNamespace(verdict=health_module.DANGER, headline="Acceptance rate 12%")
    summary = await stepdown.evaluate(db, account, health_report=danger, now=NOW)
    assert summary["check_percent"] == 100
    assert "12%" in summary["last_reset_reason"]


async def test_changing_how_comments_are_written_resets(db, warm_account):
    account = warm_account
    _set_stage(account, 3)
    stepdown._save(account, {**stepdown.state(account), "copy_fingerprint": stepdown.copy_fingerprint("openrouter:old-model")})
    row = await _comment(db, account, status=SuggestionStatus.PENDING, created_at=NOW)
    await db.commit()

    counts = await stepdown.apply_to_new(db, account, [row], rng=lambda: 0.99)
    assert counts == {"checked": 1, "auto_approved": 0}
    assert stepdown.summary(account)["check_percent"] == 100
    assert "test-model" in stepdown.summary(account)["last_reset_reason"]


async def test_reporting_a_bad_posted_comment_resets(db, account):
    waved, _ = await _at_stage_3_with_unsent_auto_approval(db, account)
    await stepdown.reset(db, account, "Bad comment reported: wrong company name")
    await db.commit()
    await db.refresh(waved)
    assert stepdown.summary(account)["check_percent"] == 100
    assert waved.status == SuggestionStatus.PENDING

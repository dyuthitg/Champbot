"""
The step-down rule: how many comments a person has to check before they post.

Agreed with Champ on 2026-10-07 (doc: "Step-down rule for comment approval").

- Stage 1 checks every comment. Stage 2 checks a random half, stage 3 a random
  1 in 5. Nothing goes below 20%.
- An account steps down a stage after 5 clean batches in a row. A batch is one
  local day's comment queue for one account; it is clean when it had at least
  10 comments, every one was reviewed or posted, and nothing was rejected for
  being wrong, off-tone or unsafe.
- Any of these puts the account straight back to stage 1 and restarts the
  count: a bad comment reported after posting, a reject for being wrong /
  off-tone / unsafe, a quality flag on a comment that would have skipped
  review, acceptance under 15% or a LinkedIn challenge (the health report's
  DANGER verdict), or a change to how comments are written (prompt or model).

Only comments are sampled. Invitations and messages stay at 100% review.

State lives on the account's ``daily_caps["_meta"]["approval"]`` blob, next to
the other operational notes (there is no separate table for these yet).
"""

from __future__ import annotations

import hashlib
import logging
import random
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.accounts import caps as caps_policy
from src.outreach.models import OutreachSuggestion, SuggestionAction, SuggestionStatus

logger = logging.getLogger(__name__)

# The agreed numbers. Changing any of these is a change to the agreed rule.
CHECK_RATE = {1: 1.0, 2: 0.5, 3: 0.2}
LOWEST_STAGE = 3
CLEAN_BATCHES_TO_STEP_DOWN = 5
MIN_BATCH_SIZE = 10

# A reject reason starting with one of these words means the comment itself was
# the problem (the doc's "Safety:" / "Tone:" convention), not just a poor fit.
PROBLEM_PREFIXES = ("safety", "tone", "wrong")

# How far back to look when counting finished days. Days older than this were
# either counted already or are too stale to matter.
_LOOKBACK_DAYS = 30
_HISTORY_LIMIT = 20

# Statuses that mean a comment in the day's batch was settled, one way or the
# other. PENDING means the day isn't finished; BLOCKED never reached anyone.
_SETTLED = (
    SuggestionStatus.APPROVED,
    SuggestionStatus.SCHEDULED,
    SuggestionStatus.SENT,
    SuggestionStatus.FAILED,
    SuggestionStatus.REJECTED,
    SuggestionStatus.EXPIRED,
    SuggestionStatus.CANCELLED,
)


# ----------------------------------------------------------------------
# State
# ----------------------------------------------------------------------


def state(account: Any) -> dict:
    """The account's current approval state, with defaults filled in."""
    meta = (getattr(account, "daily_caps", None) or {}).get("_meta") or {}
    raw = meta.get("approval") or {}
    stage = int(raw.get("stage") or 1)
    if stage not in CHECK_RATE:
        stage = 1
    return {
        "stage": stage,
        "clean_streak": int(raw.get("clean_streak") or 0),
        "last_day_counted": raw.get("last_day_counted"),
        "copy_fingerprint": raw.get("copy_fingerprint"),
        "history": list(raw.get("history") or []),
    }


def _save(account: Any, new_state: dict) -> None:
    caps = dict(getattr(account, "daily_caps", None) or {})
    meta = dict(caps.get("_meta") or {})
    new_state["history"] = new_state.get("history", [])[-_HISTORY_LIMIT:]
    meta["approval"] = new_state
    caps["_meta"] = meta
    # Reassign rather than mutate so SQLAlchemy sees the JSON column change.
    account.daily_caps = caps


def _log(current: dict, event: str, detail: str, now: datetime) -> None:
    current["history"].append({"at": now.isoformat(), "event": event, "detail": detail})


def summary(account: Any) -> dict:
    """What the UI shows: the check rate and progress to the next step."""
    current = state(account)
    stage = current["stage"]
    last_reset = next(
        (h for h in reversed(current["history"]) if h.get("event") == "reset"), None
    )
    return {
        "stage": stage,
        "check_percent": int(CHECK_RATE[stage] * 100),
        "clean_streak": current["clean_streak"],
        "clean_needed": CLEAN_BATCHES_TO_STEP_DOWN,
        "next_check_percent": (
            int(CHECK_RATE[stage + 1] * 100) if stage < LOWEST_STAGE else None
        ),
        "min_batch_size": MIN_BATCH_SIZE,
        "last_reset_reason": last_reset.get("detail") if last_reset else None,
        "last_reset_at": last_reset.get("at") if last_reset else None,
        "history": current["history"][-5:],
    }


# ----------------------------------------------------------------------
# Going back to 100%
# ----------------------------------------------------------------------


async def reset(
    db: AsyncSession, account: Any, reason: str, *, now: Optional[datetime] = None
) -> dict:
    """
    Put the account back to checking every comment, and restart the count.

    Comments that were waved through at 50%/20% but haven't posted yet go back
    into the review queue: "straight back to 100%" has to include them, or a
    reset leaves a day's worth of unchecked comments still on their way out.
    Does not commit; the caller does.
    """
    now = now or datetime.now(timezone.utc)
    current = state(account)
    was = current["stage"]
    current["stage"] = 1
    current["clean_streak"] = 0
    # Days already finished before the reset can't count toward the new streak.
    current["last_day_counted"] = caps_policy.local_now(account, now).date().isoformat()
    _log(current, "reset", reason, now)
    _save(account, current)

    unchecked = (
        await db.execute(
            select(OutreachSuggestion).where(
                OutreachSuggestion.account_id == account.id,
                OutreachSuggestion.action == SuggestionAction.COMMENT,
                OutreachSuggestion.status.in_(
                    [SuggestionStatus.APPROVED, SuggestionStatus.SCHEDULED]
                ),
            )
        )
    ).scalars().all()
    returned = 0
    for suggestion in unchecked:
        if not _was_auto_approved(suggestion):
            continue
        suggestion.status = SuggestionStatus.PENDING
        suggestion.scheduled_for = None
        suggestion.reviewed_at = None
        suggestion.result = None
        returned += 1

    if was != 1 or returned:
        logger.info(
            "Approval reset to 100%% for account %s (was stage %s, %s comments "
            "returned to review): %s",
            account.id, was, returned, reason,
        )
    return {"stage": 1, "returned_to_review": returned}


def is_problem_reject(reason: Optional[str], comment_problem: bool = False) -> bool:
    """Was this reject about the comment itself being wrong, off-tone or unsafe?"""
    if comment_problem:
        return True
    text = (reason or "").strip().lower()
    return any(text.startswith(prefix) for prefix in PROBLEM_PREFIXES)


async def on_reject(
    db: AsyncSession,
    account: Any,
    suggestion: OutreachSuggestion,
    reason: Optional[str],
    *,
    comment_problem: bool = False,
) -> bool:
    """Reset if a comment was rejected for being wrong/off-tone/unsafe."""
    if suggestion.action != SuggestionAction.COMMENT:
        return False
    if not is_problem_reject(reason, comment_problem):
        return False
    await reset(db, account, f"Comment rejected: {(reason or '').strip()}"[:300])
    return True


def _was_auto_approved(suggestion: OutreachSuggestion) -> bool:
    return bool((suggestion.result or {}).get("auto_approved"))


# ----------------------------------------------------------------------
# Writing changes
# ----------------------------------------------------------------------


def copy_fingerprint(generated_by: Optional[str]) -> str:
    """
    Identifies "how the bot writes comments": the prompt rules plus the model.

    A template fallback counts as a different writer too -- it is.
    """
    from src.outreach import copy as copywriter

    raw = f"{copywriter._STYLE_RULES}\n{generated_by or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


async def check_writer(
    db: AsyncSession, account: Any, generated_by: Optional[str]
) -> bool:
    """Reset when the comment writer changed since the last comment. Returns True on reset."""
    fingerprint = copy_fingerprint(generated_by)
    current = state(account)
    previous = current["copy_fingerprint"]
    if previous == fingerprint:
        return False
    if previous is None:
        # First comment ever seen: just remember the writer.
        current["copy_fingerprint"] = fingerprint
        _save(account, current)
        return False
    await reset(
        db, account, f"How comments are written changed (now {generated_by or 'unknown'})"
    )
    current = state(account)
    current["copy_fingerprint"] = fingerprint
    _save(account, current)
    return True


# ----------------------------------------------------------------------
# Counting clean batches
# ----------------------------------------------------------------------


async def evaluate(
    db: AsyncSession,
    account: Any,
    *,
    health_report: Any = None,
    now: Optional[datetime] = None,
) -> dict:
    """
    Bring the account's stage up to date. Does not commit; the caller does.

    1. A DANGER health verdict (acceptance under 15%, or a LinkedIn challenge)
       resets to 100%.
    2. Each finished local day since the last one counted is judged: a day
       with at least MIN_BATCH_SIZE settled comments and no problem rejects
       adds one to the streak. Smaller days neither count nor break it.
       A day with comments still waiting for review stops the count there --
       it can't be judged until someone has looked.
    3. Every CLEAN_BATCHES_TO_STEP_DOWN clean days, step down one stage.
    """
    from src.outreach import health as health_module

    now = now or datetime.now(timezone.utc)

    if health_report is None:
        health_report = await health_module.account_health(db, account)
    if getattr(health_report, "verdict", None) == health_module.DANGER:
        if state(account)["stage"] != 1:
            await reset(
                db, account, f"Account health: {getattr(health_report, 'headline', '')}", now=now
            )
        return summary(account)

    current = state(account)
    today = caps_policy.local_now(account, now).date()
    last_counted = (
        date.fromisoformat(current["last_day_counted"])
        if current["last_day_counted"]
        else None
    )

    since = now - timedelta(days=_LOOKBACK_DAYS)
    rows = (
        await db.execute(
            select(OutreachSuggestion).where(
                OutreachSuggestion.account_id == account.id,
                OutreachSuggestion.action == SuggestionAction.COMMENT,
                OutreachSuggestion.created_at >= since,
            )
        )
    ).scalars().all()

    by_day: dict = defaultdict(list)
    for row in rows:
        created = row.created_at
        if created is None:
            continue
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        day = caps_policy.local_now(account, created).date()
        if day >= today or (last_counted and day <= last_counted):
            continue
        by_day[day].append(row)

    problem_ids = await _problem_reject_ids(db, account, since)

    for day in sorted(by_day):
        batch = by_day[day]
        if any(r.status == SuggestionStatus.PENDING for r in batch):
            break  # not finished being reviewed; judge it later
        settled = [r for r in batch if r.status in _SETTLED]
        dirty = any(str(r.id) in problem_ids for r in settled)
        current["last_day_counted"] = day.isoformat()
        if dirty:
            # on_reject already reset at the time; this just keeps a day
            # judged later (e.g. after a restart) from counting as clean.
            current["clean_streak"] = 0
            continue
        if len(settled) < MIN_BATCH_SIZE:
            continue
        current["clean_streak"] += 1
        _log(current, "clean_day", f"{day.isoformat()}: {len(settled)} comments", now)
        if (
            current["clean_streak"] >= CLEAN_BATCHES_TO_STEP_DOWN
            and current["stage"] < LOWEST_STAGE
        ):
            current["stage"] += 1
            current["clean_streak"] = 0
            _log(
                current,
                "step_down",
                f"Now checking {int(CHECK_RATE[current['stage']] * 100)}% of comments",
                now,
            )

    _save(account, current)
    return summary(account)


async def _problem_reject_ids(db: AsyncSession, account: Any, since: datetime) -> set:
    """Suggestion ids whose reject was about the comment itself (from the ledger)."""
    from src.warmup.models import AccountActivity

    rows = (
        await db.execute(
            select(AccountActivity).where(
                AccountActivity.account_id == account.id,
                AccountActivity.action == "reject",
                AccountActivity.created_at >= since,
            )
        )
    ).scalars().all()
    ids = set()
    for row in rows:
        detail = row.detail or {}
        if is_problem_reject(detail.get("reason"), bool(detail.get("comment_problem"))):
            if detail.get("suggestion_id"):
                ids.add(str(detail["suggestion_id"]))
    return ids


# ----------------------------------------------------------------------
# Sampling new comments
# ----------------------------------------------------------------------


def needs_review(
    account: Any,
    suggestion: OutreachSuggestion,
    *,
    rng: Callable[[], float] = random.random,
) -> tuple:
    """
    Should a person check this new comment? Returns (needs_review, why).

    Pure: the caller acts on the answer (including the reset for a flagged
    comment, which needs the database).
    """
    if suggestion.action != SuggestionAction.COMMENT:
        return True, "not_a_comment"
    stage = state(account)["stage"]
    if stage == 1:
        return True, "stage_1"
    if suggestion.quality_warnings:
        return True, "quality_flag"
    if rng() < CHECK_RATE[stage]:
        return True, "sampled"
    return False, "not_sampled"


async def apply_to_new(
    db: AsyncSession,
    account: Any,
    suggestions: list,
    *,
    rng: Callable[[], float] = random.random,
) -> dict:
    """
    Run freshly generated, pending suggestions through the rule.

    Comments not picked for checking are approved on the rule's behalf -- they
    still go through the same quality gate, pacing and caps as a hand approval.
    """
    from src.outreach import execute as executor

    counts = {"checked": 0, "auto_approved": 0}
    for suggestion in suggestions:
        if suggestion.status != SuggestionStatus.PENDING:
            continue
        if suggestion.action != SuggestionAction.COMMENT:
            continue

        if await check_writer(db, account, suggestion.generated_by):
            counts["checked"] += 1
            continue

        review, why = needs_review(account, suggestion, rng=rng)
        if why == "quality_flag":
            await reset(
                db,
                account,
                "Quality check flagged a comment that would have skipped review: "
                + "; ".join(str(w) for w in suggestion.quality_warnings)[:200],
            )
        if review:
            counts["checked"] += 1
            continue

        try:
            stage = state(account)["stage"]
            await executor.approve(db, suggestion, account=account, auto_stage=stage)
            counts["auto_approved"] += 1
        except executor.ExecutionBlocked as exc:
            # The gate blocked it on re-check; it now sits as BLOCKED, visible.
            logger.info("Auto-approve blocked for %s: %s", suggestion.id, exc.reason)
    await db.commit()
    return counts

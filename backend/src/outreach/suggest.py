"""
The suggestion engine: decide who to talk to, draft what to say, ask the user.

This is where "don't be spammy" is actually enforced, before any network call
happens. A target has to survive every one of these gates to become a
suggestion the user ever sees:

1. **Relevance floor** — scores below the ICP's floor are dropped, not ranked
   lower. Volume is never a substitute for fit.
2. **Suppression** — anyone explicitly suppressed is untouchable, permanently.
3. **Dedupe** — one live suggestion per (target, action), and never a repeat of
   an action already sent. Nobody gets the same message twice.
4. **Remaining capacity** — we never suggest more of an action than the account
   can still legally send today under its caps.
5. **Approval budget** — a hard ceiling on suggestions per account per day.
   A 200-item queue gets rubber-stamped, which would quietly delete the entire
   value of human review.
6. **Copy quality** — drafts with blocking defects are stored as ``blocked``
   rather than shown as ready to approve.

What comes out is a small, ranked, reviewable set: the people most worth
talking to, with something specific to say to each.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.accounts import caps as caps_policy
from src.accounts.models import EngagementMode
from src.outreach import copy as copywriter
from src.outreach.models import OutreachSuggestion, SuggestionAction, SuggestionStatus
from src.targeting.models import ICPProfile, OutreachTarget, TargetStatus
from src.targeting.scoring import score_target

logger = logging.getLogger(__name__)

# Statuses that still "occupy" a target for an action, so we don't stack a
# second suggestion on top of one already in flight or already delivered.
LIVE_STATUSES = (
    SuggestionStatus.PENDING,
    SuggestionStatus.APPROVED,
    SuggestionStatus.SCHEDULED,
    SuggestionStatus.SENT,
)


class SuggestionSkipped(Exception):
    """A target was skipped, with a reason worth reporting."""


async def generate_suggestions(
    db: AsyncSession,
    account: Any,
    icp: Optional[ICPProfile] = None,
    *,
    limit: Optional[int] = None,
    provider: Any = None,
    rate_limiter: Any = None,
) -> dict:
    """
    Build today's review queue for one account.

    Returns a summary dict with the created suggestions and, importantly, the
    reasons targets were skipped — the skip reasons are the product's honesty
    surface. "We looked at 40 people and are suggesting 6" is far more useful
    than silently surfacing 6.
    """
    from src.outreach import health as health_module
    from src.warmup import service as warmup_service

    icp = icp or await _active_icp(db, account)
    if icp is None:
        return {
            "created": [],
            "considered": 0,
            "skipped": {"no_icp": 1},
            "message": "No ICP is configured for this account, so there is nobody to target.",
        }

    # Warm-up gate. An account that hasn't earned outreach yet doesn't get a
    # queue at all -- there is no point asking a human to approve invitations
    # the account is not permitted to send.
    #
    # Fixed 2026-09-02: this used to check only connect and message, so an
    # account in the "commenting" warm-up stage -- which explicitly *can*
    # comment -- got zero suggestions and a message blaming 'connect', an
    # action nobody was trying to use. Comment is a suggestable action too
    # (see `permitted` below); it belongs in this gate.
    report = await health_module.account_health(db, account)
    action_gate = {
        action: warmup_service.can_perform(account, action, report)
        for action in (SuggestionAction.CONNECT, SuggestionAction.MESSAGE, SuggestionAction.COMMENT)
    }
    permitted = {action for action, (allowed, _) in action_gate.items() if allowed}
    if not permitted:
        # All three come from the same stage gate and differ only in which
        # action name is embedded in the reason -- any one of them is honest.
        _, reason = next(iter(action_gate.values()))
        return {
            "created": [],
            "considered": 0,
            "skipped": {"warmup": 1},
            "message": reason,
        }

    budget = await _remaining_budget(db, account)
    if limit is not None:
        budget = min(budget, limit)
    if budget <= 0:
        return {
            "created": [],
            "considered": 0,
            "skipped": {"daily_suggestion_budget": 1},
            "message": "Today's suggestion budget for this account is already used.",
        }

    targets = await _candidate_targets(db, account)
    skipped: dict = {}
    scored: List[tuple] = []

    # `permitted` was already computed above, from the same action_gate.

    for target in targets:
        action = _action_for(account, target)
        if action is None:
            _bump(skipped, "no_applicable_action")
            continue
        if action not in permitted:
            _bump(skipped, f"{action}_not_unlocked_yet")
            continue

        result = score_target(target, icp)
        target.relevance_score = result.score
        target.relevance_reasons = result.reasons

        if result.excluded:
            target.status = TargetStatus.SKIPPED
            _bump(skipped, "excluded_by_icp")
            continue
        if result.score < (icp.relevance_floor or 0):
            target.status = TargetStatus.SCORED
            _bump(skipped, "below_relevance_floor")
            continue

        target.status = TargetStatus.SCORED
        scored.append((result.score, action, target))

    # Best fit first: if capacity is limited, spend it on the strongest matches.
    scored.sort(key=lambda row: row[0], reverse=True)

    # How many of each action the account may still send today, at the volume
    # its measured health allows.
    capacity = await _remaining_capacity(
        account, {a for _, a, _ in scored}, rate_limiter, throttle=report.throttle
    )

    created: List[OutreachSuggestion] = []
    for score, action, target in scored:
        if len(created) >= budget:
            _bump(skipped, "daily_suggestion_budget")
            continue
        if capacity.get(action, 0) <= 0:
            _bump(skipped, f"no_{action}_capacity_today")
            continue
        if await _already_suggested(db, target, action):
            _bump(skipped, "already_suggested")
            continue

        draft = await copywriter.draft(
            action, target, account, icp, provider=provider, org_id=str(account.org_id)
        )

        status = (
            SuggestionStatus.BLOCKED
            if draft.quality.blockers
            else SuggestionStatus.PENDING
        )

        suggestion = OutreachSuggestion(
            id=uuid.uuid4(),
            org_id=account.org_id,
            account_id=account.id,
            target_id=target.id,
            action=action,
            status=status,
            draft_text=draft.text,
            rationale=draft.rationale,
            relevance_score=score,
            relevance_reasons=target.relevance_reasons,
            quality_score=draft.quality.score,
            quality_warnings=draft.quality.all_issues,
            generated_by=draft.generated_by,
            subject_urn=_subject_urn(target, action),
        )
        db.add(suggestion)
        created.append(suggestion)

        if status == SuggestionStatus.PENDING:
            target.status = TargetStatus.SUGGESTED
            capacity[action] = capacity.get(action, 0) - 1
        else:
            _bump(skipped, "copy_quality_blocked")

    await db.commit()
    for suggestion in created:
        await db.refresh(suggestion)

    return {
        "created": created,
        "considered": len(targets),
        "skipped": skipped,
        "message": _summarize(len(created), len(targets), skipped),
    }


# ----------------------------------------------------------------------
# Gates
# ----------------------------------------------------------------------


async def _active_icp(db: AsyncSession, account: Any) -> Optional[ICPProfile]:
    """The account's chosen ICP, or its most recent active one."""
    if getattr(account, "active_icp_id", None):
        row = (
            await db.execute(
                select(ICPProfile).where(ICPProfile.id == account.active_icp_id)
            )
        ).scalar_one_or_none()
        if row is not None:
            return row

    stmt = (
        select(ICPProfile)
        .where(
            ICPProfile.org_id == account.org_id,
            ICPProfile.is_active.is_(True),
            ICPProfile.deleted_at.is_(None),
        )
        .order_by(ICPProfile.created_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


# Statuses a target may be in and still be looked at on a generation run.
#
# SKIPPED and SUGGESTED are deliberately included: an ICP can be edited, so a
# previously-excluded person must get re-scored rather than being written off
# forever, and re-considering an already-suggested person is what lets the
# dedupe gate report *why* they were skipped instead of them silently vanishing.
#
# Absent on purpose: CONTACTED and APPROVED (an action is already in flight),
# and SUPPRESSED — the user's explicit "never contact this person", which no
# amount of ICP editing may undo.
_CONSIDERABLE = (
    TargetStatus.NEW,
    TargetStatus.SCORED,
    TargetStatus.SKIPPED,
    TargetStatus.SUGGESTED,
    TargetStatus.CONNECTED,
)


async def _candidate_targets(db: AsyncSession, account: Any) -> List[OutreachTarget]:
    """Targets eligible for consideration, newest first."""
    stmt = (
        select(OutreachTarget)
        .where(
            OutreachTarget.account_id == account.id,
            OutreachTarget.status.in_(list(_CONSIDERABLE)),
        )
        .order_by(OutreachTarget.created_at.desc())
        .limit(500)
    )
    return list((await db.execute(stmt)).scalars().all())


def _action_for(account: Any, target: Any) -> Optional[str]:
    """
    Pick the right next action for this person, given the account's mode.

    OUTREACH: meet people who aren't connections yet — invite first, message
    only once they've accepted.

    ACCOUNT_BASED_ENGAGEMENT: earn attention from people already in the
    network by engaging with what they publish. Almost no cold contact.
    """
    mode = getattr(account, "mode", None) or EngagementMode.OUTREACH
    status = getattr(target, "status", None)
    context = getattr(target, "context", None) or {}
    has_post = bool(context.get("post_urn"))

    if mode == EngagementMode.ACCOUNT_BASED_ENGAGEMENT:
        if has_post:
            return SuggestionAction.COMMENT
        if status == TargetStatus.CONNECTED:
            return SuggestionAction.MESSAGE
        return None  # nothing to engage with yet; don't invent a reason to contact

    # OUTREACH
    if status == TargetStatus.CONNECTED:
        return SuggestionAction.MESSAGE
    if has_post:
        # Commenting on their post before inviting is warmer and converts far
        # better than a cold invitation.
        return SuggestionAction.COMMENT
    return SuggestionAction.CONNECT


async def _already_suggested(db: AsyncSession, target: Any, action: str) -> bool:
    """Has this person already had this action suggested or sent?"""
    stmt = select(func.count()).where(
        OutreachSuggestion.target_id == target.id,
        OutreachSuggestion.action == action,
        OutreachSuggestion.status.in_(LIVE_STATUSES),
    )
    return bool((await db.execute(stmt)).scalar() or 0)


async def _remaining_budget(db: AsyncSession, account: Any) -> int:
    """Approval budget left for this account today."""
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    stmt = select(func.count()).where(
        OutreachSuggestion.account_id == account.id,
        OutreachSuggestion.created_at >= since,
    )
    used = int((await db.execute(stmt)).scalar() or 0)
    return max(0, caps_policy.suggestion_budget(account) - used)


async def _remaining_capacity(
    account: Any, actions: set, rate_limiter: Any = None, throttle: float = 1.0
) -> dict:
    """
    How many of each action this account may still send today.

    Reads the live counters when a limiter is available so the queue reflects
    what has already gone out; falls back to the configured daily cap when it
    isn't (which only ever over-estimates the queue, never the sending — the
    executor checks the real limiter again before every send).

    The weekly window is checked alongside the daily one: invitations are
    capped weekly by LinkedIn, so an account can have daily headroom and no
    weekly headroom at all.
    """
    capacity = {}
    for action in actions:
        caps = caps_policy.caps_for(account, action, throttle=throttle)
        day_used = week_used = 0
        if rate_limiter is not None:
            try:
                usage = await rate_limiter.usage(str(account.id), action)
                day_used = int(usage.get("day_used", 0))
                week_used = int(usage.get("week_used", 0))
            except Exception as exc:  # a limiter hiccup must not block review
                logger.warning("Rate usage lookup failed for %s: %s", action, exc)

        remaining = max(0, caps.per_day - day_used)
        if caps.per_week:
            remaining = min(remaining, max(0, caps.per_week - week_used))
        capacity[action] = remaining
    return capacity


def _subject_urn(target: Any, action: str) -> Optional[str]:
    context = getattr(target, "context", None) or {}
    if action in (SuggestionAction.COMMENT, SuggestionAction.LIKE):
        return context.get("post_urn")
    return getattr(target, "member_urn", None)


def _bump(counter: dict, key: str) -> None:
    counter[key] = counter.get(key, 0) + 1


def _summarize(created: int, considered: int, skipped: dict) -> str:
    """A plain-English explanation of what the engine did and why."""
    if created == 0 and considered == 0:
        return "No targets to review yet — import or discover some people first."
    if created == 0:
        top = max(skipped.items(), key=lambda kv: kv[1])[0] if skipped else "unknown"
        return (
            f"Reviewed {considered} people and suggested none. "
            f"Most common reason: {top.replace('_', ' ')}."
        )
    parts = [f"Suggested {created} of {considered} people reviewed"]
    if skipped:
        detail = ", ".join(
            f"{count} {reason.replace('_', ' ')}"
            for reason, count in sorted(skipped.items(), key=lambda kv: -kv[1])[:3]
        )
        parts.append(f"skipped: {detail}")
    return "; ".join(parts) + "."

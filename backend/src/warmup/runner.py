"""
The warm-up runner: actually perform the day's activity.

``planner.plan_day`` decides *what and when*. This module does it. It is the
piece that turns the programme from a schedule into behaviour.

Where the activity comes from
-----------------------------
A warming account can't like random posts — that builds the wrong interest
graph and teaches LinkedIn's feed the wrong things about it. So engagement is
drawn from the account's own ICP: the recent posts of people it will eventually
want to talk to. Two benefits fall out of that:

- The feed becomes genuinely relevant, which makes later activity look natural.
- By the time an invitation is sent, the account has often already engaged with
  that person's content. A warm invitation gets accepted; a cold one gets
  reported.

What runs automatically, and what doesn't
-----------------------------------------
Split by blast radius, not convenience:

- **Likes and follows run automatically.** They are reversible, carry no text,
  and nobody has ever regretted a like.
- **Comments and posts go through the approval queue.** They are published
  under the user's name and are permanent. A bad comment on a prospect's post
  is worse than no comment, and the whole product is built on a human seeing
  outbound text before it ships.

That default is overridable per account (``warmup.auto_comment``), but it is
the default for a reason.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.accounts import caps as caps_policy
from src.accounts.service import set_status
from src.infrastructure.transports.base import TransportChallenge, TransportError
from src.targeting.models import HUMAN_OWNED, OutreachTarget
from src.warmup import planner, program
from src.warmup import service as warmup_service
from src.warmup.models import AccountActivity, ActivityStatus

logger = logging.getLogger(__name__)

# How many ICP profiles to pull activity from in one run. Fetching everyone's
# feed every tick is itself a detectable pattern.
PROFILE_SAMPLE = 8


class RunResult(dict):
    """Summary of one warm-up run."""


async def run_today(
    db: AsyncSession,
    account,
    *,
    transport: Any = None,
    rate_limiter: Any = None,
    live: Any = None,
    now: Optional[datetime] = None,
    max_actions: int = 25,
) -> dict:
    """
    Perform whatever the account is due to do right now.

    Designed to be called on a schedule (every 15-30 minutes is sensible). It
    only performs actions whose planned time has already passed, so calling it
    more often doesn't make the account act faster — the plan still paces it.
    """
    now = now or datetime.now(timezone.utc)

    assessment = await warmup_service.today(db, account, now=now)
    if assessment.get("paused"):
        return RunResult(performed=[], skipped={"paused": 1}, message="Warm-up is paused")

    plan_actions = assessment["plan"]["actions"]
    stage_key = assessment["stage"]
    throttle = float(assessment["health"].get("throttle", 1.0))

    # Only what's due. Anything scheduled later this afternoon stays there.
    due = [a for a in plan_actions if _parse(a["at"]) <= now]
    already = assessment["plan"].get("completed_today") or {}

    # Subtract what has already been done today so re-running is idempotent.
    outstanding: List[dict] = []
    remaining_by_action = {}
    for item in due:
        action = item["action"]
        if action not in remaining_by_action:
            planned = len([a for a in plan_actions if a["action"] == action])
            remaining_by_action[action] = max(0, planned - int(already.get(action, 0)))
        if remaining_by_action[action] > 0:
            outstanding.append(item)
            remaining_by_action[action] -= 1

    if not outstanding:
        return RunResult(
            performed=[],
            skipped={},
            message="Nothing due right now — the day's activity is paced out",
        )

    live = live or await _live_account(db, account)
    client = transport or _default_transport(live)

    performed: List[dict] = []
    skipped: dict = {}
    queued_for_review = 0

    feed = await _icp_feed(db, account, client, live)

    for item in outstanding[:max_actions]:
        action = item["action"]

        allowed, reason = warmup_service.can_perform(account, action)
        if not allowed:
            _bump(skipped, "not_unlocked")
            continue

        if not await _consume_slot(account, action, rate_limiter, throttle):
            _bump(skipped, f"{action}_at_cap")
            continue

        if action in (program.LIKE, program.FOLLOW):
            outcome = await _perform_auto(db, account, client, live, action, feed, stage_key)
            if outcome is None:
                _bump(skipped, f"no_{action}_target")
            elif outcome:
                performed.append({"action": action, **outcome})
            else:
                _bump(skipped, f"{action}_failed")

        elif action == program.COMMENT:
            if await _queue_comment(db, account, feed):
                queued_for_review += 1
            else:
                _bump(skipped, "no_post_to_comment_on")

        elif action == program.POST:
            _bump(skipped, "post_needs_a_draft")

    await db.commit()

    parts = []
    if performed:
        counts: dict = {}
        for p in performed:
            counts[p["action"]] = counts.get(p["action"], 0) + 1
        parts.append(", ".join(f"{v} {k}s" for k, v in counts.items()))
    if queued_for_review:
        parts.append(f"{queued_for_review} comment(s) queued for your approval")
    if not parts:
        parts.append("nothing performed")

    return RunResult(
        performed=performed,
        queued_for_review=queued_for_review,
        skipped=skipped,
        stage=stage_key,
        message="; ".join(parts),
    )


# ----------------------------------------------------------------------
# Activity sources
# ----------------------------------------------------------------------


async def _icp_feed(db: AsyncSession, account, client, live) -> List[dict]:
    """
    Recent posts from people in this account's ICP.

    Engaging with the right people's content is what makes warm-up productive
    rather than just safe: it teaches the feed, it earns profile views, and it
    means later invitations land on someone who has already seen the name.
    """
    stmt = (
        select(OutreachTarget)
        .where(
            OutreachTarget.account_id == account.id,
            OutreachTarget.status.not_in(list(HUMAN_OWNED)),
        )
        .order_by(OutreachTarget.relevance_score.desc())
        .limit(PROFILE_SAMPLE)
    )
    targets = list((await db.execute(stmt)).scalars().all())

    engaged = set(
        (
            await db.execute(
                select(AccountActivity.subject_urn).where(
                    AccountActivity.account_id == account.id,
                    AccountActivity.subject_urn.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )

    feed: List[dict] = []
    for target in targets:
        try:
            result = await client.fetch_activity(live, target.member_urn)
        except TransportError as exc:
            logger.debug("Activity fetch failed for %s: %s", target.member_urn, exc)
            continue
        if not result.success:
            continue

        for post in (result.detail or {}).get("posts", []) or []:
            urn = post.get("urn")
            if not urn or urn in engaged:
                continue
            feed.append(
                {
                    "urn": urn,
                    "text": post.get("text"),
                    "target_id": target.id,
                    "member_urn": target.member_urn,
                    "name": target.full_name,
                    "target": target,
                }
            )

    return feed


async def _perform_auto(
    db: AsyncSession, account, client, live, action: str, feed: List[dict], stage: str
) -> Optional[dict]:
    """Perform a like or a follow. Returns None when there was nothing to act on."""
    if action == program.LIKE:
        item = _take(feed)
        if item is None:
            return None
        subject, target_id, label = item["urn"], item["target_id"], item.get("name")
        call = client.like(live, subject)
    else:
        item = _take(feed)
        if item is None:
            return None
        subject, target_id, label = item["member_urn"], item["target_id"], item.get("name")
        call = client.follow(live, subject)

    try:
        result = await call
    except TransportChallenge as exc:
        from src.accounts.models import AccountStatus

        set_status(account, AccountStatus.RATE_LIMITED)
        await warmup_service.record(
            db, account, action, status=ActivityStatus.BLOCKED,
            subject_urn=subject, error=str(exc), commit=False,
        )
        logger.warning("Account %s challenged during warm-up: %s", account.id, exc)
        return {}
    except TransportError as exc:
        await warmup_service.record(
            db, account, action, status=ActivityStatus.FAILED,
            subject_urn=subject, target_id=target_id, error=str(exc), commit=False,
        )
        return {}

    await warmup_service.record(
        db,
        account,
        action,
        status=ActivityStatus.OK if result.success else ActivityStatus.FAILED,
        subject_urn=subject,
        target_id=target_id,
        detail={"via": result.via},
        error=None if result.success else result.error,
        commit=False,
    )
    if not result.success:
        return {}
    return {"subject": subject, "who": label}


async def _queue_comment(db: AsyncSession, account, feed: List[dict]) -> bool:
    """
    Draft a comment and put it in the approval queue.

    Comments are published under the user's name and can't be taken back, so
    they get the same human review as outreach — the small extra friction is
    what keeps a warming account from embarrassing anybody.
    """
    item = _take(feed)
    if item is None:
        return False

    from src.outreach import copy as copywriter
    from src.outreach.models import OutreachSuggestion, SuggestionAction, SuggestionStatus
    from src.targeting.models import ICPProfile

    icp = (
        await db.execute(
            select(ICPProfile)
            .where(ICPProfile.org_id == account.org_id, ICPProfile.is_active.is_(True))
            .limit(1)
        )
    ).scalar_one_or_none()

    target = item["target"]
    # Give the copywriter the post it is replying to, so the comment is about
    # what they actually said rather than about them in general.
    context = dict(getattr(target, "context", None) or {})
    context.update({"post_urn": item["urn"], "post_text": item.get("text")})
    target.context = context

    draft = await copywriter.draft(
        SuggestionAction.COMMENT, target, account, icp, org_id=str(account.org_id)
    )

    db.add(
        OutreachSuggestion(
            id=uuid.uuid4(),
            org_id=account.org_id,
            account_id=account.id,
            target_id=target.id,
            action=SuggestionAction.COMMENT,
            status=(
                SuggestionStatus.BLOCKED
                if draft.quality.blockers
                else SuggestionStatus.PENDING
            ),
            draft_text=draft.text,
            rationale=f"Warm-up engagement on a post by {target.full_name or 'an ICP contact'}",
            relevance_score=target.relevance_score or 0,
            relevance_reasons=target.relevance_reasons or [],
            quality_score=draft.quality.score,
            quality_warnings=draft.quality.all_issues,
            generated_by=draft.generated_by,
            subject_urn=item["urn"],
            step="warmup_comment",
        )
    )
    return True


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _take(feed: List[dict]) -> Optional[dict]:
    """Pop the next unused item from the feed."""
    return feed.pop(0) if feed else None


async def _consume_slot(account, action: str, rate_limiter, throttle: float) -> bool:
    """Check the global cap. No limiter means we can't prove safety, so refuse."""
    if rate_limiter is None:
        import os

        return os.getenv("ALLOW_UNCAPPED_SENDING", "").lower() == "true"

    caps = caps_policy.caps_for(account, action, throttle=throttle)
    decision = await rate_limiter.check_and_consume(
        str(account.id),
        action,
        per_hour=caps.per_hour,
        per_day=caps.per_day,
        per_week=caps.per_week,
        cooldown_seconds=caps.cooldown_seconds,
    )
    return bool(decision.allowed)


async def _live_account(db: AsyncSession, account):
    from src.accounts.service import load_live_account

    return await load_live_account(db, str(account.id))


def _default_transport(live):
    from src.infrastructure.api_client import get_transport

    return get_transport(live)


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _bump(counter: dict, key: str) -> None:
    counter[key] = counter.get(key, 0) + 1

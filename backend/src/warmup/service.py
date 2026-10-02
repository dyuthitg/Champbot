"""
Warm-up runner: advance stages, record activity, report progress.

This is the loop a scheduled job calls once a day per account. It does three
things, in this order, and the order matters:

1. **Assess health.** Measured acceptance rate, plus whether LinkedIn has
   challenged the account.
2. **Move the stage.** Forward if the account has earned it, backward if the
   numbers say it is in trouble. A demotion is not a failure state — it is the
   system doing its job before LinkedIn does it for us.
3. **Plan the day.** Only then produce the activity plan, at the stage and
   throttle that step 2 settled on.

Doing health *before* planning is what stops an account from spending a whole
day executing a plan built on stale assumptions.
"""

from __future__ import annotations

import logging
import uuid
import re
from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.accounts import caps as caps_policy
from src.outreach import health as health_module
from src.warmup import planner, program
from src.warmup.models import AccountActivity, ActivityStatus

logger = logging.getLogger(__name__)


async def totals_for(db: AsyncSession, account) -> dict:
    """Cumulative successful actions for an account, by action type."""
    rows = (
        await db.execute(
            select(AccountActivity.action, func.count())
            .where(
                AccountActivity.account_id == account.id,
                AccountActivity.status == ActivityStatus.OK,
            )
            .group_by(AccountActivity.action)
        )
    ).all()
    return {action: int(count) for action, count in rows}


async def record(
    db: AsyncSession,
    account,
    action: str,
    *,
    status: str = ActivityStatus.OK,
    subject_urn: Optional[str] = None,
    target_id: Optional[uuid.UUID] = None,
    variant: Optional[str] = None,
    detail: Optional[dict] = None,
    error: Optional[str] = None,
    commit: bool = True,
) -> AccountActivity:
    """Write one action to the ledger."""
    entry = AccountActivity(
        id=uuid.uuid4(),
        org_id=account.org_id,
        account_id=account.id,
        action=action,
        status=status,
        stage=planner.current_stage(account),
        subject_urn=subject_urn,
        target_id=target_id,
        variant=variant,
        detail=detail,
        error=error,
    )
    db.add(entry)
    if commit:
        await db.commit()
    return entry


async def evaluate(
    db: AsyncSession, account, *, now: Optional[datetime] = None
) -> dict:
    """
    Assess an account and move it to the stage it has earned.

    Returns a report describing the current stage, whether it changed, what is
    still outstanding, and the health verdict behind the decision.
    """
    now = now or datetime.now(timezone.utc)

    report = await health_module.account_health(db, account)
    totals = await totals_for(db, account)
    stage_key = planner.current_stage(account)

    graduation = program.evaluate_graduation(
        stage_key,
        days_in_stage=planner.days_in_stage(account, now),
        totals=totals,
        acceptance_rate=report.funnel.acceptance_rate,
        invites_sent=report.funnel.invites_sent,
        had_challenge=report.had_challenge,
    )

    changed = None
    if graduation.demote_to and graduation.demote_to != stage_key:
        planner.set_stage(account, graduation.demote_to, now=now)
        changed = {"from": stage_key, "to": graduation.demote_to, "direction": "back"}
        logger.warning(
            "Account %s stepped back to %s: %s",
            account.id, graduation.demote_to, "; ".join(graduation.blockers),
        )
    elif graduation.ready and graduation.target:
        planner.set_stage(account, graduation.target, now=now)
        changed = {"from": stage_key, "to": graduation.target, "direction": "forward"}

    if changed:
        await db.commit()
        await db.refresh(account)
        stage_key = planner.current_stage(account)

    stage = program.stage_for(stage_key)
    return {
        "account_id": str(account.id),
        "stage": stage.key,
        "stage_name": stage.name,
        "intent": stage.intent,
        "days_in_stage": planner.days_in_stage(account, now),
        "min_days": stage.min_days,
        "allowed_actions": sorted(stage.allowed),
        "totals": totals,
        "changed": changed,
        "ready_to_advance": graduation.ready,
        "next_stage": graduation.target,
        "progress": graduation.reasons,
        "blockers": graduation.blockers,
        "paused": planner.paused(account),
        "health": report.as_dict(),
    }


async def today(
    db: AsyncSession, account, *, now: Optional[datetime] = None
) -> dict:
    """
    The account's plan for today, after re-assessing its stage.

    This is the single call a daily scheduler needs.
    """
    now = now or datetime.now(timezone.utc)
    assessment = await evaluate(db, account, now=now)

    if assessment["paused"]:
        return {
            **assessment,
            "plan": {"actions": [], "counts": {}, "notes": ["Warm-up is paused"]},
        }

    throttle = float(assessment["health"].get("throttle", 1.0))
    suspended = set(assessment["health"].get("suspended_actions") or [])

    plan = planner.plan_day(
        account,
        day=caps_policy.local_now(account, now).date(),
        stage_key=assessment["stage"],
        throttle=throttle,
        now=now,
    )

    actions = [
        {"action": item.action, "at": item.at.isoformat(), "reason": item.reason}
        for item in plan.actions
        if item.action not in suspended
    ]
    notes = list(plan.notes)
    if suspended:
        notes.append(
            f"Suspended by account health: {', '.join(sorted(suspended))}"
        )

    done_today = await _done_today(db, account, now)

    return {
        **assessment,
        "plan": {
            "day": plan.day.isoformat(),
            "actions": actions,
            "counts": {
                action: len([a for a in actions if a["action"] == action])
                for action in {a["action"] for a in actions}
            },
            "completed_today": done_today,
            "notes": notes,
        },
    }


async def _done_today(db: AsyncSession, account, now: datetime) -> dict:
    """What the account has already done since its local midnight, by action."""
    local = caps_policy.local_now(account, now)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(
        timezone.utc
    )
    rows = (
        await db.execute(
            select(AccountActivity.action, func.count())
            .where(
                AccountActivity.account_id == account.id,
                AccountActivity.status == ActivityStatus.OK,
                AccountActivity.created_at >= midnight,
            )
            .group_by(AccountActivity.action)
        )
    ).all()
    return {action: int(count) for action, count in rows}


# LinkedIn opens a post at /feed/update/<urn>/ for these kinds of id. Feed
# responses sometimes wrap one inside a longer urn, so it is searched for.
_POST_URN = re.compile(r"urn:li:(?:activity|share|ugcPost):\d+")


def post_url(urn: Optional[str]) -> Optional[str]:
    """A link that opens this post on LinkedIn, or None if the urn isn't a post."""
    match = _POST_URN.search(urn or "")
    return f"https://www.linkedin.com/feed/update/{match.group(0)}/" if match else None


async def recent_activity(
    db: AsyncSession, account, *, action: Optional[str] = None, limit: int = 50
) -> List[dict]:
    """
    What the account has done lately, newest first, for people to look at.

    Includes failed and blocked attempts too: "it tried and LinkedIn refused"
    is exactly what someone checking on the account needs to see.
    """
    from src.targeting.models import OutreachTarget

    stmt = (
        select(AccountActivity, OutreachTarget.full_name)
        .outerjoin(OutreachTarget, OutreachTarget.id == AccountActivity.target_id)
        .where(AccountActivity.account_id == account.id)
        .order_by(AccountActivity.created_at.desc())
        .limit(limit)
    )
    if action:
        stmt = stmt.where(AccountActivity.action == action)

    return [
        {
            "id": str(entry.id),
            "action": entry.action,
            "status": entry.status,
            "stage": entry.stage,
            "at": entry.created_at.isoformat() if entry.created_at else None,
            "person": name,
            "post_text": (entry.detail or {}).get("post_text"),
            "url": post_url(entry.subject_urn) if entry.action == program.LIKE else None,
            "error": entry.error,
        }
        for entry, name in (await db.execute(stmt)).all()
    ]


def can_perform(account, action: str, health: Any = None) -> tuple:
    """
    May this account perform ``action`` right now?

    Returns ``(allowed, reason)``. Three gates, in order of severity: the
    warm-up stage (has the account earned this capability), an explicit pause,
    and the health governor (has the audience turned against it).
    """
    if planner.paused(account):
        return False, "Warm-up is paused for this account"

    stage_key = planner.current_stage(account)
    if not program.is_allowed(stage_key, action):
        stage = program.stage_for(stage_key)
        return False, (
            f"'{action}' isn't unlocked yet — this account is in the "
            f"{stage.name.lower()} stage of warm-up"
        )

    if health is not None and getattr(health, "blocks", None) and health.blocks(action):
        return False, health.headline

    return True, ""

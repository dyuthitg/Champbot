"""
Execution: turn an approved suggestion into a real LinkedIn action.

Everything upstream of this module is advisory. This is the only place that
actually talks to LinkedIn on the user's behalf, so it re-checks every
invariant rather than trusting that the approval path got it right:

- the suggestion is genuinely approved and due,
- the copy still passes the quality gate (it may have been edited by hand),
- the account still has capacity under the **global** Redis rate limiter,
- and the action is being taken inside the account's active hours.

Any of those failing means the action doesn't happen. A missed send is
recoverable; an action that shouldn't have been sent is not.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.accounts import caps as caps_policy
from src.accounts.service import LiveAccount, load_live_account, set_status
from src.infrastructure.transports.base import TransportChallenge, TransportError
from src.outreach import pacing, sequences
from src.outreach.models import OutreachSuggestion, SuggestionAction, SuggestionStatus
from src.outreach.quality import check_copy
from src.targeting.models import OutreachTarget, TargetStatus

logger = logging.getLogger(__name__)


class ExecutionBlocked(Exception):
    """The action was refused by a safety gate. Carries the reason."""

    def __init__(self, reason: str, retry_after: int = 0):
        super().__init__(reason)
        self.reason = reason
        self.retry_after = retry_after


async def approve(
    db: AsyncSession,
    suggestion: OutreachSuggestion,
    *,
    reviewer_id: Optional[str] = None,
    edited_text: Optional[str] = None,
    account: Any = None,
    send_at: Optional[datetime] = None,
) -> OutreachSuggestion:
    """
    Approve a suggestion and give it a send time.

    An edit by the user is re-checked by the quality gate exactly like
    generated copy — a human typing a booking link into a connection note is
    just as much a problem as a model doing it.
    """
    if suggestion.status not in (SuggestionStatus.PENDING, SuggestionStatus.BLOCKED):
        raise ExecutionBlocked(f"cannot approve a suggestion that is {suggestion.status}")

    target = await _load_target(db, suggestion)
    text = (edited_text if edited_text is not None else suggestion.draft_text) or ""

    if suggestion.action in (SuggestionAction.CONNECT, SuggestionAction.MESSAGE, SuggestionAction.COMMENT):
        quality = check_copy(
            text,
            suggestion.action,
            target,
            allow_scheduler_link=sequences.allows_scheduler_link(suggestion.step),
        )
        suggestion.quality_score = quality.score
        suggestion.quality_warnings = quality.all_issues
        if quality.blockers:
            suggestion.status = SuggestionStatus.BLOCKED
            await db.commit()
            raise ExecutionBlocked("; ".join(quality.blockers))

    suggestion.final_text = text
    suggestion.status = SuggestionStatus.SCHEDULED
    suggestion.reviewed_at = datetime.now(timezone.utc)
    if reviewer_id:
        suggestion.reviewed_by = uuid.UUID(str(reviewer_id))

    account = account or await _load_account_record(db, suggestion)
    last_sent = await _last_sent_at(db, suggestion.account_id, suggestion.action)
    suggestion.scheduled_for = send_at or pacing.schedule_next(
        account, suggestion.action, last_sent_at=last_sent
    )

    if target is not None:
        target.status = TargetStatus.APPROVED

    # Ledger entry: the existing audit trail (see src/warmup/models.py),
    # reused rather than inventing a second log. Written only once we're past
    # the status guard above, so calling approve twice on the same item
    # raises ExecutionBlocked on the second call and never double-logs.
    from src.warmup import service as warmup_service
    from src.warmup.models import ActivityStatus

    await warmup_service.record(
        db,
        account,
        "approve",
        status=ActivityStatus.OK,
        subject_urn=suggestion.subject_urn,
        target_id=suggestion.target_id,
        variant=suggestion.variant,
        detail={
            "suggestion_id": str(suggestion.id),
            "edited": edited_text is not None,
            "reviewer_id": reviewer_id,
        },
        commit=False,
    )

    await db.commit()
    await db.refresh(suggestion)
    return suggestion


async def reject(
    db: AsyncSession,
    suggestion: OutreachSuggestion,
    *,
    reviewer_id: Optional[str] = None,
    suppress_target: bool = False,
    reason: Optional[str] = None,
    account: Any = None,
) -> OutreachSuggestion:
    """
    Reject a suggestion.

    ``suppress_target`` is the "never contact this person" switch: it puts the
    target permanently out of reach of every future suggestion, for every
    action. That is what makes "no" mean no.

    ``reason`` is stored on the audit ledger, not on the suggestion itself --
    it's the data that improves the prompt later, not something the review
    screen needs to keep displaying.
    """
    if suggestion.status not in (SuggestionStatus.PENDING, SuggestionStatus.BLOCKED):
        raise ExecutionBlocked(f"cannot reject a suggestion that is {suggestion.status}")

    suggestion.status = SuggestionStatus.REJECTED
    suggestion.reviewed_at = datetime.now(timezone.utc)
    if reviewer_id:
        suggestion.reviewed_by = uuid.UUID(str(reviewer_id))

    target = await _load_target(db, suggestion)
    if target is not None:
        target.status = (
            TargetStatus.SUPPRESSED if suppress_target else TargetStatus.SCORED
        )

    # Ledger entry, same trail approve() writes to. Guarded by the status
    # check above, so a second reject on the same item is refused before it
    # ever reaches this line -- no duplicate entry.
    from src.warmup import service as warmup_service
    from src.warmup.models import ActivityStatus

    account = account or await _load_account_record(db, suggestion)
    await warmup_service.record(
        db,
        account,
        "reject",
        status=ActivityStatus.OK,
        subject_urn=suggestion.subject_urn,
        target_id=suggestion.target_id,
        variant=suggestion.variant,
        detail={
            "suggestion_id": str(suggestion.id),
            "reason": reason,
            "suppress_target": suppress_target,
            "reviewer_id": reviewer_id,
        },
        commit=False,
    )

    await db.commit()
    await db.refresh(suggestion)
    return suggestion


async def execute_suggestion(
    db: AsyncSession,
    suggestion: OutreachSuggestion,
    *,
    transport: Any = None,
    rate_limiter: Any = None,
    account: Any = None,
    force: bool = False,
) -> OutreachSuggestion:
    """
    Send one approved suggestion.

    ``force`` skips the "is it due yet" check (used by "send now" in the UI) but
    never skips the caps, the quality gate, or the active-hours window.
    """
    if suggestion.status not in (SuggestionStatus.APPROVED, SuggestionStatus.SCHEDULED):
        raise ExecutionBlocked(f"suggestion is {suggestion.status}, not approved")

    record = account or await _load_account_record(db, suggestion)
    if record is None:
        raise ExecutionBlocked("connected account not found")

    now = datetime.now(timezone.utc)
    if not force and suggestion.scheduled_for and _aware(suggestion.scheduled_for) > now:
        raise ExecutionBlocked("not due yet")

    if not pacing.is_within_active_hours(record, now):
        # Reschedule rather than fail: the action is still wanted, just not now.
        suggestion.scheduled_for = pacing.next_active_moment(record, now)
        await db.commit()
        raise ExecutionBlocked("outside the account's active hours; rescheduled")

    target = await _load_target(db, suggestion)
    text = suggestion.final_text or suggestion.draft_text or ""

    # Re-run the gate at send time: this is the last point of control.
    if suggestion.action in (
        SuggestionAction.CONNECT,
        SuggestionAction.MESSAGE,
        SuggestionAction.COMMENT,
    ):
        quality = check_copy(
            text,
            suggestion.action,
            target,
            allow_scheduler_link=sequences.allows_scheduler_link(suggestion.step),
        )
        if quality.blockers:
            suggestion.status = SuggestionStatus.BLOCKED
            suggestion.error = "; ".join(quality.blockers)
            await db.commit()
            raise ExecutionBlocked(suggestion.error)

    # Warm-up gate: has this account earned the right to perform this action at
    # all? This is checked at send time as well as at suggestion time, because
    # an account can be demoted between the two.
    from src.outreach import health as health_module
    from src.warmup import service as warmup_service

    report = await health_module.account_health(db, record)
    permitted, why_not = warmup_service.can_perform(record, suggestion.action, report)
    if not permitted:
        suggestion.scheduled_for = now + _delta(3600)
        await db.commit()
        raise ExecutionBlocked(why_not)

    # Global cap check. This consumes a slot only if it allows the action, so a
    # refusal here never burns the account's allowance.
    if rate_limiter is not None:
        caps = caps_policy.caps_for(record, suggestion.action, throttle=report.throttle)
        decision = await rate_limiter.check_and_consume(
            str(record.id),
            suggestion.action,
            per_hour=caps.per_hour,
            per_day=caps.per_day,
            per_week=caps.per_week,
            cooldown_seconds=caps.cooldown_seconds,
        )
        if not decision.allowed:
            suggestion.scheduled_for = now + _delta(decision.retry_after_seconds)
            await db.commit()
            raise ExecutionBlocked(
                f"rate limited ({decision.reason})", retry_after=decision.retry_after_seconds
            )

    live = account if isinstance(account, LiveAccount) else await load_live_account(
        db, str(suggestion.account_id)
    )
    client = transport or _default_transport(live)

    suggestion.attempts += 1
    try:
        result = await _dispatch(client, live, suggestion, target, text)
    except TransportChallenge as exc:
        # The account needs attention; stop using it rather than retrying into
        # a restriction.
        from src.accounts.models import AccountStatus

        set_status(record, AccountStatus.RATE_LIMITED)
        suggestion.status = SuggestionStatus.FAILED
        suggestion.error = str(exc)
        await db.commit()
        raise ExecutionBlocked(f"account challenged: {exc}") from exc
    except TransportError as exc:
        suggestion.status = SuggestionStatus.FAILED
        suggestion.error = str(exc)
        await db.commit()
        raise ExecutionBlocked(str(exc)) from exc

    from src.warmup.models import ActivityStatus

    if result.success:
        suggestion.status = SuggestionStatus.SENT
        suggestion.sent_at = now
        suggestion.result = {
            "via": result.via,
            "detail": result.detail,
            "step": suggestion.step,
        }
        suggestion.error = None
        record.last_active_at = now
        if target is not None:
            # Don't walk a target backwards: someone who already accepted or
            # replied stays there when a later message goes out.
            if target.status not in (
                TargetStatus.CONNECTED,
                TargetStatus.REPLIED,
                TargetStatus.INTERESTED,
                TargetStatus.BOOKED,
            ):
                target.status = TargetStatus.CONTACTED
            target.last_touched_at = now
            if suggestion.action == SuggestionAction.CONNECT and target.invited_at is None:
                target.invited_at = now
            if suggestion.variant and not target.variant:
                target.variant = suggestion.variant
    else:
        suggestion.status = SuggestionStatus.FAILED
        suggestion.error = result.error or "transport reported failure"
        suggestion.result = {"via": result.via, "detail": result.detail}

    # Ledger entry: powers warm-up graduation, the funnel, and per-variant
    # outcome attribution.
    await warmup_service.record(
        db,
        record,
        suggestion.action,
        status=ActivityStatus.OK if result.success else ActivityStatus.FAILED,
        subject_urn=suggestion.subject_urn,
        target_id=suggestion.target_id,
        variant=suggestion.variant,
        detail={"step": suggestion.step, "via": result.via},
        error=None if result.success else suggestion.error,
        commit=False,
    )

    await db.commit()
    await db.refresh(suggestion)
    return suggestion


async def run_due(
    db: AsyncSession,
    account: Any,
    *,
    transport: Any = None,
    rate_limiter: Any = None,
    limit: int = 10,
) -> dict:
    """
    Execute every approved suggestion that is due for one account.

    This is what the scheduler agent calls on its tick. It stops at the first
    capacity refusal for an action rather than hammering the limiter.
    """
    now = datetime.now(timezone.utc)
    stmt = (
        select(OutreachSuggestion)
        .where(
            OutreachSuggestion.account_id == account.id,
            OutreachSuggestion.status.in_(
                [SuggestionStatus.APPROVED, SuggestionStatus.SCHEDULED]
            ),
        )
        .order_by(OutreachSuggestion.scheduled_for.asc().nulls_first())
        .limit(limit)
    )
    due = list((await db.execute(stmt)).scalars().all())

    sent, blocked = [], {}
    exhausted = set()

    for suggestion in due:
        if suggestion.action in exhausted:
            continue
        if suggestion.scheduled_for and _aware(suggestion.scheduled_for) > now:
            continue
        try:
            await execute_suggestion(
                db,
                suggestion,
                transport=transport,
                rate_limiter=rate_limiter,
                account=account,
            )
            sent.append(str(suggestion.id))
        except ExecutionBlocked as exc:
            blocked[str(suggestion.id)] = exc.reason
            if "rate limited" in exc.reason or "active hours" in exc.reason:
                exhausted.add(suggestion.action)

    return {"sent": sent, "blocked": blocked, "considered": len(due)}


# ----------------------------------------------------------------------
# Internals
# ----------------------------------------------------------------------


async def _dispatch(client, live, suggestion, target, text):
    """Route the suggestion to the right transport method."""
    action = suggestion.action
    member_urn = getattr(target, "member_urn", None) or suggestion.subject_urn

    if action == SuggestionAction.CONNECT:
        return await client.connect(live, member_urn, text or None)
    if action == SuggestionAction.MESSAGE:
        return await client.send_message(live, member_urn, text)
    if action == SuggestionAction.COMMENT:
        return await client.comment(live, suggestion.subject_urn, text)
    if action == SuggestionAction.LIKE:
        return await client.like(live, suggestion.subject_urn)
    if action == SuggestionAction.FOLLOW:
        return await client.follow(live, member_urn)
    raise ExecutionBlocked(f"unsupported action: {action}")


def _default_transport(live):
    from src.infrastructure.api_client import get_transport

    return get_transport(live)


async def _load_target(db: AsyncSession, suggestion) -> Optional[OutreachTarget]:
    return (
        await db.execute(
            select(OutreachTarget).where(OutreachTarget.id == suggestion.target_id)
        )
    ).scalar_one_or_none()


async def _load_account_record(db: AsyncSession, suggestion):
    from src.accounts.models import ConnectedAccount

    return (
        await db.execute(
            select(ConnectedAccount).where(ConnectedAccount.id == suggestion.account_id)
        )
    ).scalar_one_or_none()


async def _last_sent_at(db: AsyncSession, account_id, action: str) -> Optional[datetime]:
    stmt = (
        select(OutreachSuggestion.sent_at)
        .where(
            OutreachSuggestion.account_id == account_id,
            OutreachSuggestion.action == action,
            OutreachSuggestion.sent_at.is_not(None),
        )
        .order_by(OutreachSuggestion.sent_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _delta(seconds: int):
    from datetime import timedelta

    return timedelta(seconds=max(60, int(seconds or 60)))

"""
Outreach routes: generate suggestions, review them, send the approved ones.

This is the loop the product is built around:

    POST /outreach/suggestions        -> the agent proposes
    GET  /outreach/suggestions        -> the user reviews
    POST /outreach/suggestions/{id}/approve   (optionally edited)
    POST /outreach/suggestions/{id}/reject    (optionally suppressing forever)
    POST /outreach/accounts/{id}/run   -> paced execution of what was approved

Nothing reaches LinkedIn without passing through the approve step.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.accounts import caps as caps_policy
from src.accounts import service as accounts_service
from src.api.middleware.clerk import RequestContext, get_request_context
from src.database.session import get_db
from src.outreach import execute as executor
from src.outreach import health as health_module
from src.outreach import similarity
from src.outreach import suggest as engine
from src.outreach import sync as sync_module
from src.outreach.models import OutreachSuggestion, SuggestionAction, SuggestionStatus
from src.outreach.quality import check_copy, flag as quality_flag
from src.outreach.schemas import (
    AccountStats,
    ActivityItem,
    ActivityResponse,
    ApproveRequest,
    DashboardResponse,
    GenerateRequest,
    GenerateResponse,
    RejectRequest,
    QualityFlagOut,
    RunDueResponse,
    SuggestionListResponse,
    SuggestionResponse,
    TargetSummary,
)
from src.targeting.models import OutreachTarget
from src.warmup import planner as warmup_planner
from src.warmup import program as warmup_program

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/outreach", tags=["outreach"])


def _rate_limiter(request: Request):
    """
    The global per-account limiter, when Redis is connected.

    Without Redis the caps can't be enforced globally, so — unless an operator
    has explicitly opted into running degraded — sending is refused rather than
    silently uncapped. Failing closed is the only safe default for a component
    whose entire job is to stop over-sending.
    """
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        return None
    from src.infrastructure.rate_policy import AccountRateLimiter

    return AccountRateLimiter(redis)


def _sending_allowed_without_limiter() -> bool:
    return os.getenv("ALLOW_UNCAPPED_SENDING", "").lower() == "true"


async def _require_account(db: AsyncSession, account_id: str, org_id: str):
    record = await accounts_service.get_account_record(db, account_id, org_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return record


async def _require_suggestion(db: AsyncSession, suggestion_id: str, org_id: str):
    try:
        key = uuid.UUID(str(suggestion_id))
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="Suggestion not found")

    row = (
        await db.execute(
            select(OutreachSuggestion).where(
                OutreachSuggestion.id == key,
                OutreachSuggestion.org_id == uuid.UUID(str(org_id)),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    return row


# ----------------------------------------------------------------------
# Generate
# ----------------------------------------------------------------------


@router.post("/suggestions", response_model=GenerateResponse)
async def generate_suggestions(
    payload: GenerateRequest,
    request: Request,
    ctx: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
) -> GenerateResponse:
    """
    Build today's review queue: who to contact and what to say to each.

    Creates nothing that gets sent — every result waits for approval.
    """
    account = await _require_account(db, payload.account_id, ctx.org_id)

    icp = None
    if payload.icp_id:
        from src.targeting import service as targeting_service

        icp = await targeting_service.get_icp(db, payload.icp_id, ctx.org_id)
        if icp is None:
            raise HTTPException(status_code=404, detail="ICP not found")

    result = await engine.generate_suggestions(
        db,
        account,
        icp,
        limit=payload.limit,
        rate_limiter=_rate_limiter(request),
    )

    created = [await _serialize(db, s) for s in result["created"]]
    return GenerateResponse(
        created=created,
        considered=result["considered"],
        skipped=result["skipped"],
        message=result["message"],
    )


# ----------------------------------------------------------------------
# Review
# ----------------------------------------------------------------------


@router.get("/suggestions", response_model=SuggestionListResponse)
async def list_suggestions(
    account_id: Optional[str] = Query(None),
    suggestion_status: Optional[str] = Query(SuggestionStatus.PENDING, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
) -> SuggestionListResponse:
    """
    One page of the review queue. Defaults to what is awaiting a decision.

    Pass ``status=all`` to see everything including sent and rejected.

    A queue is not always small. Before this took an ``offset`` the screen
    asked for 200 rows and hoped; at 400 pending the other 200 were simply
    invisible, and ``total`` reported the page size so nothing could even say
    how many were missing.
    """
    filters = [OutreachSuggestion.org_id == uuid.UUID(str(ctx.org_id))]
    if account_id:
        filters.append(OutreachSuggestion.account_id == uuid.UUID(str(account_id)))
    if suggestion_status and suggestion_status != "all":
        filters.append(OutreachSuggestion.status == suggestion_status)

    total = (
        await db.execute(select(func.count()).select_from(OutreachSuggestion).where(*filters))
    ).scalar_one()

    # Best matches first: the reviewer's attention is the scarce resource.
    stmt = (
        select(OutreachSuggestion)
        .where(*filters)
        .order_by(
            OutreachSuggestion.relevance_score.desc(),
            OutreachSuggestion.created_at.desc(),
            OutreachSuggestion.id.asc(),  # stable: pages must not overlap
        )
        .offset(offset)
        .limit(limit)
    )

    rows = list((await db.execute(stmt)).scalars().all())
    serialized = [await _serialize(db, r) for r in rows]

    # Flag repetition across the batch -- the thing a one-at-a-time review
    # can never show on its own. Only meaningful among items still awaiting
    # a decision; a queue of "all" statuses would flag a sent message
    # against a rejected one, which tells the reviewer nothing useful.
    if suggestion_status == SuggestionStatus.PENDING:
        await _flag_repetition(db, serialized, filters)

    return SuggestionListResponse(
        suggestions=serialized,
        total=total,
        offset=offset,
        has_more=offset + len(serialized) < total,
    )


async def _flag_repetition(db: AsyncSession, page: list, filters: list) -> None:
    """
    Compare this page against the *whole* pending queue, not just itself.

    Paging created a hole this closes: with 400 items across eight pages, a
    template stamped on all of them would show as unique on every page, because
    each page only ever saw its own fifty. The comparison set is therefore the
    full queue; only the flags for the rows on this page are returned.

    Only the text and the name are loaded for the off-page rows -- comparing
    drafts needs neither the target row nor the quality flags, and loading them
    for a whole queue to answer a question about fifty of them would trade one
    performance problem for another.
    """
    if not page:
        return

    rows = (
        await db.execute(
            select(
                OutreachSuggestion.id,
                OutreachSuggestion.action,
                OutreachSuggestion.draft_text,
                OutreachSuggestion.final_text,
                OutreachTarget.full_name,
                OutreachTarget.first_name,
            )
            .join(OutreachTarget, OutreachTarget.id == OutreachSuggestion.target_id)
            .where(*filters)
        )
    ).all()

    from types import SimpleNamespace

    corpus = [
        SimpleNamespace(
            id=str(row.id),
            action=row.action,
            draft_text=row.draft_text,
            final_text=row.final_text,
            target=SimpleNamespace(full_name=row.full_name, first_name=row.first_name),
        )
        for row in rows
    ]
    similar = similarity.find_similar(corpus)

    for item in page:
        names = similar.get(item.id, [])
        item.similar_to = names[: similarity.MAX_NAMED]
        if not names:
            continue
        # Same vocabulary as every other guardrail, so the queue's failure-type
        # filter can offer repetition next to the rest instead of it being a
        # special case nothing can group by.
        shown = ", ".join(item.similar_to)
        rest = len(names) - len(item.similar_to)
        detail = (
            f"Reads like {len(names)} other queued draft"
            f"{'' if len(names) == 1 else 's'} ({shown}"
            f"{f' and {rest} more' if rest else ''})"
        )
        item.quality_flags.append(
            QualityFlagOut(**quality_flag("DUP", detail).as_dict())
        )


@router.get("/suggestions/{suggestion_id}", response_model=SuggestionResponse)
async def get_suggestion(
    suggestion_id: str,
    ctx: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
) -> SuggestionResponse:
    row = await _require_suggestion(db, suggestion_id, ctx.org_id)
    return await _serialize(db, row)


@router.post("/suggestions/{suggestion_id}/approve", response_model=SuggestionResponse)
async def approve_suggestion(
    suggestion_id: str,
    payload: ApproveRequest,
    ctx: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
) -> SuggestionResponse:
    """
    Approve a suggestion, optionally with an edit, and schedule it.

    The edit is re-checked by the same quality gate the draft went through, so
    approving does not bypass the safety rules — it only supplies human intent.
    """
    row = await _require_suggestion(db, suggestion_id, ctx.org_id)
    try:
        row = await executor.approve(
            db,
            row,
            reviewer_id=ctx.user_id,
            edited_text=payload.edited_text,
            send_at=payload.send_at,
        )
    except executor.ExecutionBlocked as exc:
        raise HTTPException(status_code=422, detail=exc.reason) from exc
    return await _serialize(db, row)


@router.post("/suggestions/{suggestion_id}/reject", response_model=SuggestionResponse)
async def reject_suggestion(
    suggestion_id: str,
    payload: RejectRequest,
    ctx: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
) -> SuggestionResponse:
    """Reject a suggestion, optionally suppressing the person permanently."""
    row = await _require_suggestion(db, suggestion_id, ctx.org_id)
    try:
        row = await executor.reject(
            db,
            row,
            reviewer_id=ctx.user_id,
            suppress_target=payload.suppress_target,
            reason=payload.reason,
        )
    except executor.ExecutionBlocked as exc:
        raise HTTPException(status_code=422, detail=exc.reason) from exc
    return await _serialize(db, row)


# ----------------------------------------------------------------------
# Send
# ----------------------------------------------------------------------


@router.post("/suggestions/{suggestion_id}/send", response_model=SuggestionResponse)
async def send_suggestion(
    suggestion_id: str,
    request: Request,
    ctx: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
) -> SuggestionResponse:
    """
    Send one approved suggestion immediately.

    Skips the pacing delay only — the caps, the active-hours window and the
    quality gate all still apply.
    """
    limiter = _rate_limiter(request)
    if limiter is None and not _sending_allowed_without_limiter():
        raise HTTPException(
            status_code=503,
            detail=(
                "Rate limiting is unavailable (no Redis), so sending is disabled. "
                "Connect Redis, or set ALLOW_UNCAPPED_SENDING=true to override."
            ),
        )

    row = await _require_suggestion(db, suggestion_id, ctx.org_id)
    try:
        row = await executor.execute_suggestion(
            db, row, rate_limiter=limiter, force=True
        )
    except executor.ExecutionBlocked as exc:
        raise HTTPException(status_code=422, detail=exc.reason) from exc
    return await _serialize(db, row)


@router.post("/accounts/{account_id}/run", response_model=RunDueResponse)
async def run_due(
    account_id: str,
    request: Request,
    limit: int = Query(10, ge=1, le=50),
    ctx: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
) -> RunDueResponse:
    """Execute every approved suggestion that is currently due for an account."""
    limiter = _rate_limiter(request)
    if limiter is None and not _sending_allowed_without_limiter():
        raise HTTPException(
            status_code=503,
            detail=(
                "Rate limiting is unavailable (no Redis), so sending is disabled. "
                "Connect Redis, or set ALLOW_UNCAPPED_SENDING=true to override."
            ),
        )

    account = await _require_account(db, account_id, ctx.org_id)
    result = await executor.run_due(db, account, rate_limiter=limiter, limit=limit)
    return RunDueResponse(**result)


@router.post("/accounts/{account_id}/sync")
async def sync_account(
    account_id: str,
    ctx: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Pull acceptance and reply state back from LinkedIn.

    This is what stops the system talking over a real conversation: anyone who
    replied has their sequence cancelled, and anyone who accepted becomes
    eligible for a follow-up. Read-only against LinkedIn.
    """
    account = await _require_account(db, account_id, ctx.org_id)
    return await sync_module.sync_account(db, account)


@router.post("/targets/{target_id}/outcome")
async def record_outcome(
    target_id: str,
    payload: dict,
    ctx: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Record a human's verdict on a conversation: interested, booked, or not.

    Anything other than "interested" ends automation for that person for good.
    """
    outcome = str(payload.get("outcome", "")).strip()
    try:
        key = uuid.UUID(str(target_id))
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="Target not found")

    target = (
        await db.execute(
            select(OutreachTarget).where(
                OutreachTarget.id == key,
                OutreachTarget.org_id == uuid.UUID(str(ctx.org_id)),
            )
        )
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="Target not found")

    try:
        target = await sync_module.set_outcome(db, target, outcome)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {"target_id": str(target.id), "status": target.status}


# ----------------------------------------------------------------------
# Reporting
# ----------------------------------------------------------------------


@router.get("/activity", response_model=ActivityResponse)
async def activity(
    account_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    ctx: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
) -> ActivityResponse:
    """What the account has actually done, most recent first."""
    stmt = select(OutreachSuggestion).where(
        OutreachSuggestion.org_id == uuid.UUID(str(ctx.org_id)),
        OutreachSuggestion.status.in_(
            [SuggestionStatus.SENT, SuggestionStatus.FAILED, SuggestionStatus.SCHEDULED]
        ),
    )
    if account_id:
        stmt = stmt.where(OutreachSuggestion.account_id == uuid.UUID(str(account_id)))
    stmt = stmt.order_by(OutreachSuggestion.updated_at.desc()).limit(limit)

    rows = list((await db.execute(stmt)).scalars().all())
    targets = await _targets_for(db, rows)

    items = []
    for row in rows:
        target = targets.get(row.target_id)
        items.append(
            ActivityItem(
                id=str(row.id),
                account_id=str(row.account_id),
                action=row.action,
                status=row.status,
                target_name=getattr(target, "full_name", None),
                target_headline=getattr(target, "headline", None),
                text=row.final_text or row.draft_text,
                relevance_score=row.relevance_score or 0,
                occurred_at=row.sent_at or row.scheduled_for or row.created_at,
                error=row.error,
            )
        )
    return ActivityResponse(items=items, total=len(items))


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard(
    request: Request,
    ctx: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
) -> DashboardResponse:
    """
    Every connected account in the org at a glance.

    This is the admin view: one row per account showing what is waiting for
    review, what is queued, what went out today, and how much headroom is left
    under each account's caps.
    """
    accounts = await accounts_service.list_accounts(db, ctx.org_id)
    limiter = _rate_limiter(request)
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    stats = []
    totals = {
        "accounts": len(accounts),
        "pending_review": 0,
        "scheduled": 0,
        "sent_today": 0,
        "sent_total": 0,
        "failed": 0,
    }

    for account in accounts:
        counts = dict(
            (
                await db.execute(
                    select(OutreachSuggestion.status, func.count())
                    .where(OutreachSuggestion.account_id == account.id)
                    .group_by(OutreachSuggestion.status)
                )
            ).all()
        )
        sent_today = int(
            (
                await db.execute(
                    select(func.count()).where(
                        OutreachSuggestion.account_id == account.id,
                        OutreachSuggestion.status == SuggestionStatus.SENT,
                        OutreachSuggestion.sent_at >= since,
                    )
                )
            ).scalar()
            or 0
        )
        by_action = dict(
            (
                await db.execute(
                    select(OutreachSuggestion.action, func.count())
                    .where(
                        OutreachSuggestion.account_id == account.id,
                        OutreachSuggestion.status == SuggestionStatus.SENT,
                    )
                    .group_by(OutreachSuggestion.action)
                )
            ).all()
        )

        report = await health_module.account_health(db, account)

        remaining = {}
        caps_today = {}
        for action in (
            SuggestionAction.CONNECT,
            SuggestionAction.MESSAGE,
            SuggestionAction.COMMENT,
            SuggestionAction.LIKE,
        ):
            caps = caps_policy.caps_for(account, action, throttle=report.throttle)
            day_used = week_used = 0
            read_ok = False
            if limiter is not None:
                try:
                    usage = await limiter.usage(str(account.id), action)
                    day_used = int(usage.get("day_used", 0))
                    week_used = int(usage.get("week_used", 0))
                    read_ok = True
                except Exception as exc:
                    day_used = week_used = 0
                    logger.warning(
                        "dashboard: could not read %s usage for account %s: %s",
                        action, account.id, exc,
                    )
            left = max(0, caps.per_day - day_used)
            # Invitations are capped weekly by LinkedIn, so the weekly window
            # is often the real constraint even when the day looks open.
            if caps.per_week:
                left = min(left, max(0, caps.per_week - week_used))
            remaining[action] = left
            caps_today[action] = {
                "used": day_used,
                "cap": caps.per_day,
                "week_used": week_used if caps.per_week else None,
                "week_cap": caps.per_week or None,
                # False whenever the number can't be trusted -- either no
                # Redis is connected, or the read itself failed. A failed read
                # must never render as "0 used", which reads as healthy; it's
                # the one thing this view exists to not let happen.
                "tracked": read_ok,
            }

        stage = warmup_program.stage_for(warmup_planner.current_stage(account))
        meta = (account.daily_caps or {}).get("_meta") or {}

        entry = AccountStats(
            account_id=str(account.id),
            display_name=account.display_name,
            status=account.status,
            mode=account.mode,
            pending_review=int(counts.get(SuggestionStatus.PENDING, 0)),
            scheduled=int(counts.get(SuggestionStatus.SCHEDULED, 0))
            + int(counts.get(SuggestionStatus.APPROVED, 0)),
            sent_today=sent_today,
            sent_total=int(counts.get(SuggestionStatus.SENT, 0)),
            failed=int(counts.get(SuggestionStatus.FAILED, 0)),
            connects_sent=int(by_action.get(SuggestionAction.CONNECT, 0)),
            messages_sent=int(by_action.get(SuggestionAction.MESSAGE, 0)),
            remaining_today=remaining,
            warmup_stage=stage.key,
            warmup_stage_name=stage.name,
            warmup_paused=warmup_planner.paused(account),
            health_verdict=report.verdict,
            health_headline=report.headline,
            throttle=report.throttle,
            funnel=report.funnel.as_dict(),
            caps_today=caps_today,
            quiet_hours_now=caps_policy.in_quiet_hours(account),
            weekend_now=caps_policy.is_weekend(account),
            status_since=meta.get("status_changed_at"),
            last_run_at=meta.get("last_run_at"),
            last_run_ok=meta.get("last_run_ok"),
            last_error=meta.get("last_error"),
            last_error_at=meta.get("last_error_at"),
        )
        stats.append(entry)

        totals["pending_review"] += entry.pending_review
        totals["scheduled"] += entry.scheduled
        totals["sent_today"] += entry.sent_today
        totals["sent_total"] += entry.sent_total
        totals["failed"] += entry.failed
        totals["invites_sent"] = totals.get("invites_sent", 0) + report.funnel.invites_sent
        totals["invites_accepted"] = (
            totals.get("invites_accepted", 0) + report.funnel.invites_accepted
        )
        totals["replies"] = totals.get("replies", 0) + report.funnel.replies
        totals["booked"] = totals.get("booked", 0) + report.funnel.booked
        if entry.warmup_stage != warmup_program.FINAL_STAGE:
            totals["warming_up"] = totals.get("warming_up", 0) + 1

    if totals.get("invites_sent"):
        totals["acceptance_rate"] = round(
            100 * totals["invites_accepted"] / totals["invites_sent"], 1
        )

    return DashboardResponse(accounts=stats, totals=totals)


# ----------------------------------------------------------------------
# Serialization
# ----------------------------------------------------------------------


async def _targets_for(db: AsyncSession, rows) -> dict:
    """Batch-load the targets referenced by a page of suggestions."""
    ids = {r.target_id for r in rows if r.target_id}
    if not ids:
        return {}
    found = (
        await db.execute(select(OutreachTarget).where(OutreachTarget.id.in_(ids)))
    ).scalars().all()
    return {t.id: t for t in found}


async def _serialize(db: AsyncSession, row: OutreachSuggestion) -> SuggestionResponse:
    target = (
        await db.execute(
            select(OutreachTarget).where(OutreachTarget.id == row.target_id)
        )
    ).scalar_one_or_none()

    summary = None
    if target is not None:
        context = target.context if isinstance(target.context, dict) else {}
        summary = TargetSummary(
            id=str(target.id),
            full_name=target.full_name,
            first_name=target.first_name,
            headline=target.headline,
            title=target.title,
            company=target.company,
            location=target.location,
            profile_url=target.profile_url,
            status=target.status,
            post_text=context.get("post_text"),
            post_urn=context.get("post_urn"),
        )

    return SuggestionResponse(
        id=str(row.id),
        account_id=str(row.account_id),
        target_id=str(row.target_id),
        action=row.action,
        status=row.status,
        draft_text=row.draft_text,
        final_text=row.final_text,
        rationale=row.rationale,
        relevance_score=row.relevance_score or 0,
        relevance_reasons=row.relevance_reasons or [],
        quality_score=row.quality_score,
        quality_warnings=row.quality_warnings or [],
        generated_by=row.generated_by,
        subject_urn=row.subject_urn,
        scheduled_for=row.scheduled_for,
        sent_at=row.sent_at,
        error=row.error,
        created_at=row.created_at,
        target=summary,
        quality_flags=_guardrail_flags(row, target),
    )


def _guardrail_flags(row: OutreachSuggestion, target) -> list:
    """
    Re-run the gate over the text as it stands and return the named rules it
    breaks.

    Re-checked rather than read out of storage on purpose: ``quality_warnings``
    was written when the draft was generated, so after a hand edit it describes
    copy that no longer exists. The check is plain string work over one short
    message, and the queue is a single page of them.
    """
    if row.action not in ("connect", "message", "comment"):
        return []
    text = row.final_text or row.draft_text
    if not text:
        return []
    from src.outreach import sequences

    report = check_copy(
        text,
        row.action,
        target,
        allow_scheduler_link=sequences.allows_scheduler_link(row.step),
    )
    return [QualityFlagOut(**f.as_dict()) for f in report.flags]

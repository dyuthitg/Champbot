"""
Warm-up routes: the programme, an account's position in it, and today's plan.

``GET /warmup/program`` is deliberately unauthenticated — it describes the
schedule itself, which is a product explanation rather than customer data, and
being able to show someone the ramp before they connect an account is the point.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.accounts import service as accounts_service
from src.api.middleware.clerk import RequestContext, get_request_context
from src.database.session import get_db
from src.outreach import sequences
from src.warmup import planner, program
from src.warmup import service as warmup_service

router = APIRouter(prefix="/warmup", tags=["warmup"])


class PauseRequest(BaseModel):
    paused: bool = True
    reason: str = Field("", max_length=500)


class StageOverride(BaseModel):
    stage: str = Field(..., description="Stage key to move this account to")


@router.get("/program")
async def get_program() -> dict:
    """
    The warm-up programme every new account follows.

    Returns the stages, what each unlocks, the daily volume bands, and the
    cadence that runs once outreach is unlocked.
    """
    return {
        "stages": program.describe_program(),
        "minimum_days_to_outreach": program.estimated_days_to_outreach(),
        "sequence": sequences.describe_sequence(),
        "acceptance_thresholds": {
            "caution_below": program.ACCEPTANCE_CAUTION,
            "danger_below": program.ACCEPTANCE_DANGER,
        },
        "principles": [
            "Capability is earned, not configured: an action absent from the "
            "current stage cannot be performed at all, not merely throttled.",
            "Graduation needs elapsed time AND completed activity AND a healthy "
            "acceptance rate — time alone is what gets accounts restricted.",
            "A LinkedIn challenge or an acceptance rate under 15% steps the "
            "account back a stage automatically.",
            "A prospect reply stops their sequence immediately and permanently.",
        ],
    }


@router.get("/accounts/{account_id}")
async def account_status(
    account_id: str,
    ctx: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Where this account is in the programme, and what's outstanding."""
    account = await accounts_service.get_account_record(db, account_id, ctx.org_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return await warmup_service.evaluate(db, account)


@router.get("/accounts/{account_id}/today")
async def account_today(
    account_id: str,
    ctx: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Today's activity plan: what this account should do, and when.

    Re-assesses the stage first, so the plan always reflects current health.
    """
    account = await accounts_service.get_account_record(db, account_id, ctx.org_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return await warmup_service.today(db, account)


@router.post("/accounts/{account_id}/run")
async def run_warmup(
    account_id: str,
    request: Request,
    ctx: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Perform whatever this account is due to do right now.

    Safe to call on a short interval — only actions whose planned time has
    passed are performed, and work already done today is subtracted, so calling
    it more often does not make the account act faster.

    Likes and follows happen directly. Comments are drafted and placed in the
    approval queue, because they are published under the user's name.
    """
    from src.warmup import runner

    account = await accounts_service.get_account_record(db, account_id, ctx.org_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")

    redis = getattr(request.app.state, "redis", None)
    limiter = None
    if redis is not None:
        from src.infrastructure.rate_policy import AccountRateLimiter

        limiter = AccountRateLimiter(redis)
    elif os.getenv("ALLOW_UNCAPPED_SENDING", "").lower() != "true":
        raise HTTPException(
            status_code=503,
            detail=(
                "Rate limiting is unavailable (no Redis), so warm-up activity is "
                "disabled. Connect Redis, or set ALLOW_UNCAPPED_SENDING=true."
            ),
        )

    return await runner.run_today(db, account, rate_limiter=limiter)


@router.post("/accounts/{account_id}/pause")
async def pause(
    account_id: str,
    payload: PauseRequest,
    ctx: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Pause or resume all warm-up and outreach activity for an account."""
    account = await accounts_service.get_account_record(db, account_id, ctx.org_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")

    planner.set_paused(account, payload.paused, payload.reason)
    await db.commit()
    return {"account_id": account_id, "paused": payload.paused, "reason": payload.reason}


@router.post("/accounts/{account_id}/stage")
async def override_stage(
    account_id: str,
    payload: StageOverride,
    ctx: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Move an account to a specific stage.

    Intended for accounts with existing history that don't need the full ramp —
    an established profile can reasonably start further along. Skipping ahead on
    a genuinely new account is how accounts get restricted, so the response says
    so rather than silently accepting it.
    """
    account = await accounts_service.get_account_record(db, account_id, ctx.org_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    if payload.stage not in program.STAGES_BY_KEY:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown stage '{payload.stage}'. Valid: "
            + ", ".join(program.STAGES_BY_KEY),
        )

    previous = planner.current_stage(account)
    planner.set_stage(account, payload.stage)
    await db.commit()

    keys = list(program.STAGES_BY_KEY)
    skipped_ahead = keys.index(payload.stage) > keys.index(previous) + 1

    return {
        "account_id": account_id,
        "from": previous,
        "to": payload.stage,
        "warning": (
            "You skipped stages. This is safe for an established account with real "
            "history, and risky for a new one — a quiet account that suddenly starts "
            "sending is the strongest predictor of a restriction."
            if skipped_ahead
            else None
        ),
    }

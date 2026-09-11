"""
Targeting routes: define who matters, and load the people who might be them.

``POST /api/v1/targeting/preview`` is worth calling out — it scores a
hypothetical person against a draft ICP without saving anything, so the user
can tune their targeting and immediately see who it would and wouldn't reach.
Getting the ICP right is the difference between outreach and spam, and it
should not take a live send to find out it was wrong.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.accounts import service as accounts_service
from src.api.middleware.clerk import RequestContext, get_request_context
from src.database.session import get_db
from src.outreach import brand_voice as brand_voice_module
from src.targeting import service as targeting_service
from src.targeting.schemas import (
    BrandVoiceSummary,
    ICPCreate,
    ICPResponse,
    ICPUpdate,
    ScorePreviewRequest,
    ScorePreviewResponse,
    TargetImportRequest,
    TargetImportResponse,
    TargetListResponse,
    TargetResponse,
)
from src.targeting.scoring import score_target

router = APIRouter(prefix="/targeting", tags=["targeting"])


# ----------------------------------------------------------------------
# Brand voice
# ----------------------------------------------------------------------


@router.get("/brand-voices", response_model=list[BrandVoiceSummary])
async def list_brand_voices() -> list[BrandVoiceSummary]:
    """
    Every brand voice a marketer has dropped into config/brand_voices/.

    Not backed by the database -- these are files, on purpose, so adding one
    never requires a migration or a deploy. See that folder's README.md.
    """
    return [
        BrandVoiceSummary(id=p.id, brand_name=p.brand_name, formality=p.formality)
        for p in brand_voice_module.list_profiles()
    ]


# ----------------------------------------------------------------------
# ICP
# ----------------------------------------------------------------------


@router.post("/icps", response_model=ICPResponse, status_code=status.HTTP_201_CREATED)
async def create_icp(
    payload: ICPCreate,
    ctx: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
) -> ICPResponse:
    """Define an ideal customer profile."""
    icp = await targeting_service.create_icp(db, ctx.org_id, payload)
    return targeting_service.icp_to_response(icp)


@router.get("/icps", response_model=list[ICPResponse])
async def list_icps(
    ctx: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
) -> list[ICPResponse]:
    icps = await targeting_service.list_icps(db, ctx.org_id)
    return [targeting_service.icp_to_response(i) for i in icps]


@router.patch("/icps/{icp_id}", response_model=ICPResponse)
async def update_icp(
    icp_id: str,
    payload: ICPUpdate,
    ctx: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
) -> ICPResponse:
    icp = await targeting_service.get_icp(db, icp_id, ctx.org_id)
    if icp is None:
        raise HTTPException(status_code=404, detail="ICP not found")
    icp = await targeting_service.update_icp(db, icp, payload)
    return targeting_service.icp_to_response(icp)


@router.delete(
    "/icps/{icp_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def delete_icp(
    icp_id: str,
    ctx: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
) -> None:
    icp = await targeting_service.get_icp(db, icp_id, ctx.org_id)
    if icp is None:
        raise HTTPException(status_code=404, detail="ICP not found")
    await targeting_service.delete_icp(db, icp)


@router.post("/preview", response_model=ScorePreviewResponse)
async def preview_score(payload: ScorePreviewRequest) -> ScorePreviewResponse:
    """
    Score one hypothetical person against a draft ICP. Saves nothing.

    Unauthenticated on purpose: it touches no stored data and is the fastest
    way for someone to understand how targeting behaves before committing.
    """
    result = score_target(payload.target, payload.icp)
    return ScorePreviewResponse(
        score=result.score,
        reasons=result.reasons,
        excluded=result.excluded,
        exclusion_reason=result.exclusion_reason,
        passes_floor=(not result.excluded and result.score >= payload.icp.relevance_floor),
    )


# ----------------------------------------------------------------------
# Targets
# ----------------------------------------------------------------------


@router.post("/targets", response_model=TargetImportResponse)
async def import_targets(
    payload: TargetImportRequest,
    ctx: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
) -> TargetImportResponse:
    """
    Import prospects for an account, scoring them against an ICP as they land.

    People already on file for this account are skipped, so re-importing a list
    can never produce duplicate outreach.
    """
    account = await accounts_service.get_account_record(db, payload.account_id, ctx.org_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")

    icp = None
    icp_id = payload.icp_id or (str(account.active_icp_id) if account.active_icp_id else None)
    if icp_id:
        icp = await targeting_service.get_icp(db, icp_id, ctx.org_id)

    created, duplicates = await targeting_service.import_targets(
        db,
        org_id=ctx.org_id,
        account_id=payload.account_id,
        items=payload.targets,
        icp=icp,
    )
    return TargetImportResponse(
        imported=len(created),
        duplicates=duplicates,
        scored=len(created) if icp else 0,
        targets=[targeting_service.target_to_response(t) for t in created],
    )


@router.get("/targets", response_model=TargetListResponse)
async def list_targets(
    account_id: Optional[str] = Query(None),
    target_status: Optional[str] = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
    ctx: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
) -> TargetListResponse:
    """Prospects, best fit first."""
    targets = await targeting_service.list_targets(
        db,
        org_id=ctx.org_id,
        account_id=account_id,
        status=target_status,
        limit=limit,
    )
    return TargetListResponse(
        targets=[targeting_service.target_to_response(t) for t in targets],
        total=len(targets),
    )


@router.post("/targets/{target_id}/suppress", response_model=TargetResponse)
async def suppress_target(
    target_id: str,
    ctx: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
) -> TargetResponse:
    """Never contact this person again, on any account action."""
    import uuid as _uuid

    from sqlalchemy import select

    from src.targeting.models import OutreachTarget

    try:
        key = _uuid.UUID(str(target_id))
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="Target not found")

    target = (
        await db.execute(
            select(OutreachTarget).where(
                OutreachTarget.id == key,
                OutreachTarget.org_id == _uuid.UUID(str(ctx.org_id)),
            )
        )
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="Target not found")

    target = await targeting_service.suppress_target(db, target)
    return targeting_service.target_to_response(target)

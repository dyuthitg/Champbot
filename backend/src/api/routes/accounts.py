"""
Connected-account routes.

``POST /api/v1/accounts`` is the front door of the whole product: it takes a
LinkedIn session, proves it works against the live API, and returns an account
that everything else hangs off. Credentials are write-only — no endpoint here
ever returns auth material.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.accounts import service as accounts_service
from src.accounts.crypto import EncryptionUnavailable
from src.accounts.models import AccountStatus
from src.accounts.schemas import (
    AccountConnect,
    AccountHealth,
    AccountListResponse,
    AccountResponse,
    AccountRotateAuth,
    AccountUpdate,
)
from src.api.middleware.clerk import RequestContext, get_request_context
from src.database.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/accounts", tags=["accounts"])


async def _require(db: AsyncSession, account_id: str, org_id: str):
    record = await accounts_service.get_account_record(db, account_id, org_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return record


@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def connect_account(
    payload: AccountConnect,
    ctx: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
) -> AccountResponse:
    """
    Connect a LinkedIn identity using its session cookies.

    Returns 201 whether or not verification succeeded; check ``status`` on the
    response — ``active`` means the session works, ``auth_required`` means the
    cookie was rejected and needs replacing.
    """
    try:
        record = await accounts_service.connect_account(
            db, org_id=ctx.org_id, user_id=ctx.user_id, payload=payload
        )
    except EncryptionUnavailable as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except accounts_service.AccountError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return accounts_service.to_response(record)


@router.get("", response_model=AccountListResponse)
async def list_accounts(
    ctx: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
) -> AccountListResponse:
    """Every connected account in the caller's organization."""
    records = await accounts_service.list_accounts(db, ctx.org_id)
    return AccountListResponse(
        accounts=[accounts_service.to_response(r) for r in records],
        total=len(records),
    )


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: str,
    ctx: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
) -> AccountResponse:
    record = await _require(db, account_id, ctx.org_id)
    return accounts_service.to_response(record)


@router.patch("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: str,
    payload: AccountUpdate,
    ctx: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
) -> AccountResponse:
    """Update engagement mode, caps, active ICP or status."""
    record = await _require(db, account_id, ctx.org_id)
    try:
        record = await accounts_service.update_account(db, record, payload)
    except accounts_service.AccountError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return accounts_service.to_response(record)


@router.post("/{account_id}/credentials", response_model=AccountResponse)
async def rotate_credentials(
    account_id: str,
    payload: AccountRotateAuth,
    ctx: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
) -> AccountResponse:
    """Replace expired session cookies and re-verify, keeping all settings."""
    record = await _require(db, account_id, ctx.org_id)
    record = await accounts_service.rotate_credentials(db, record, payload)
    return accounts_service.to_response(record)


@router.post("/{account_id}/verify", response_model=AccountHealth)
async def verify_account(
    account_id: str,
    ctx: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
) -> AccountHealth:
    """Check the stored session against LinkedIn right now."""
    record = await _require(db, account_id, ctx.org_id)
    result = await accounts_service.check_health(db, record)
    return AccountHealth(**result)


@router.post("/{account_id}/preflight")
async def preflight(
    account_id: str,
    ctx: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Prove a live account works, using read-only calls only.

    Runs whoami plus the profile/inbox/activity probes. Nothing is liked,
    connected, messaged or posted — this is safe to run against a production
    account at any time, and is the right first step after tying one in.
    """
    from src.accounts.preflight import run_preflight

    record = await _require(db, account_id, ctx.org_id)
    report = await run_preflight(record)

    # A successful probe means the session is good; keep the stored status in
    # step with what we just observed.
    if report.ok and record.status != AccountStatus.ACTIVE:
        accounts_service.set_status(record, AccountStatus.ACTIVE)
        await db.commit()
    elif not report.ok:
        accounts_service.set_status(record, AccountStatus.AUTH_REQUIRED)
        await db.commit()

    return report.as_dict()


@router.delete(
    "/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def disconnect_account(
    account_id: str,
    ctx: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Disconnect the account and destroy its stored credentials."""
    record = await _require(db, account_id, ctx.org_id)
    await accounts_service.disconnect_account(db, record)

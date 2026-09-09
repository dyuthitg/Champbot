"""
Connected-account service: connect, verify, list, update, disconnect.

Connecting an account is the gate to everything else in the product, so it does
real work rather than just writing a row: the supplied session is used to call
LinkedIn's ``/me`` immediately, and the account is only marked ACTIVE if that
call comes back with an identity. A cookie that doesn't work is caught here,
not three days later when outreach silently stops.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.accounts import caps as caps_policy
from src.accounts.crypto import decrypt_auth, encrypt_auth
from src.accounts.models import AccountStatus, ConnectedAccount, EngagementMode
from src.accounts.schemas import AccountResponse
from src.infrastructure.transports.base import TransportError
from src.infrastructure.transports.fingerprints import generate_fingerprint

logger = logging.getLogger(__name__)


class AccountError(Exception):
    """Account operation failed in a way the caller should surface."""


class LiveAccount:
    """
    A ``ConnectedAccount`` with its credentials decrypted, shaped for transports.

    Transports duck-type on ``id``/``auth_blob``/``device_fingerprint``/``proxy``.
    Keeping the decrypted material on a short-lived object (rather than mutating
    the ORM row) means plaintext can never be accidentally flushed to the DB.
    """

    __slots__ = ("id", "auth_blob", "device_fingerprint", "proxy", "record")

    def __init__(self, record: ConnectedAccount, auth_blob: Optional[str]):
        self.id = str(record.id)
        self.auth_blob = auth_blob
        self.device_fingerprint = record.device_fingerprint
        self.proxy = record.proxy
        self.record = record

    def __repr__(self) -> str:  # keep credentials out of logs and tracebacks
        return f"<LiveAccount {self.id} credentials=redacted>"


def _transport_for(account: Any, transport: Any = None):
    """Build the transport for an account unless one was injected (tests)."""
    if transport is not None:
        return transport
    from src.infrastructure.api_client import get_transport

    return get_transport(account)


async def load_live_account(
    db: AsyncSession, account_id: str, org_id: Optional[str] = None
) -> LiveAccount:
    """Load an account and decrypt its credentials for a transport call."""
    record = await get_account_record(db, account_id, org_id)
    if record is None:
        raise AccountError("account not found")
    return LiveAccount(record, decrypt_auth(record.auth_blob))


async def get_account_record(
    db: AsyncSession, account_id: str, org_id: Optional[str] = None
) -> Optional[ConnectedAccount]:
    """Fetch one account row, scoped to an org when given."""
    try:
        key = uuid.UUID(str(account_id))
    except (ValueError, AttributeError, TypeError):
        return None

    stmt = select(ConnectedAccount).where(
        ConnectedAccount.id == key, ConnectedAccount.deleted_at.is_(None)
    )
    if org_id:
        stmt = stmt.where(ConnectedAccount.org_id == uuid.UUID(str(org_id)))
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_accounts(db: AsyncSession, org_id: str) -> list[ConnectedAccount]:
    """All non-deleted accounts in an org, newest first."""
    stmt = (
        select(ConnectedAccount)
        .where(
            ConnectedAccount.org_id == uuid.UUID(str(org_id)),
            ConnectedAccount.deleted_at.is_(None),
        )
        .order_by(ConnectedAccount.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def connect_account(
    db: AsyncSession,
    *,
    org_id: str,
    user_id: str,
    payload,
    transport: Any = None,
) -> ConnectedAccount:
    """
    Register a LinkedIn identity and verify it against the live API.

    The account row is created first (so its id seeds a stable device
    fingerprint), then verified. A failed verification still persists the
    account — in ``auth_required`` status with a recorded error — so the user
    can fix the cookie instead of losing their configuration.
    """
    record = ConnectedAccount(
        id=uuid.uuid4(),
        org_id=uuid.UUID(str(org_id)),
        user_id=uuid.UUID(str(user_id)),
        status=AccountStatus.INACTIVE,
        mode=payload.mode or EngagementMode.OUTREACH,
        display_name=payload.label,
    )

    creds = {"li_at": payload.li_at.strip()}
    if payload.jsessionid:
        creds["jsessionid"] = payload.jsessionid.strip().strip('"')
    record.auth_blob = encrypt_auth(creds)

    # A stable device identity, derived from the account id so it survives
    # restarts and is never regenerated (LinkedIn ties trust to device stability).
    record.device_fingerprint = generate_fingerprint(str(record.id))
    record.proxy = {"url": payload.proxy_url} if payload.proxy_url else None

    caps = caps_policy.default_caps_payload()
    if payload.timezone:
        caps["timezone"] = payload.timezone
    record.daily_caps = caps

    # Every new account enters the warm-up programme at the first stage. This
    # is not configurable at connect time on purpose: an account that starts
    # sending on day one is the single most restrictable thing in the system.
    from src.warmup import planner as warmup_planner
    from src.warmup import program as warmup_program

    warmup_planner.set_stage(record, warmup_program.FIRST_STAGE)

    db.add(record)
    await db.flush()

    await _verify_and_apply(record, creds, transport)

    await db.commit()
    await db.refresh(record)
    return record


async def rotate_credentials(
    db: AsyncSession,
    record: ConnectedAccount,
    payload,
    transport: Any = None,
) -> ConnectedAccount:
    """Replace an account's session cookies and re-verify."""
    creds = {"li_at": payload.li_at.strip()}
    if payload.jsessionid:
        creds["jsessionid"] = payload.jsessionid.strip().strip('"')
    record.auth_blob = encrypt_auth(creds)

    await _verify_and_apply(record, creds, transport)
    await db.commit()
    await db.refresh(record)
    return record


async def _verify_and_apply(
    record: ConnectedAccount, creds: dict, transport: Any = None
) -> None:
    """Call ``whoami`` and fold the result onto the account row."""
    live = LiveAccount(record, creds)
    try:
        result = await _transport_for(live, transport).whoami(live)
    except TransportError as exc:
        set_status(record, AccountStatus.AUTH_REQUIRED)
        _note(record, "verification_error", str(exc))
        logger.warning("Account %s failed verification: %s", record.id, exc)
        return
    except Exception as exc:  # unexpected: still don't lose the account
        set_status(record, AccountStatus.ERROR)
        _note(record, "verification_error", str(exc))
        logger.exception("Account %s verification raised", record.id)
        return

    if not result.success:
        set_status(record, AccountStatus.AUTH_REQUIRED)
        _note(record, "verification_error", result.error or "whoami failed")
        return

    detail = result.detail or {}
    set_status(record, AccountStatus.ACTIVE)
    record.linkedin_member_urn = detail.get("member_urn") or record.linkedin_member_urn
    record.profile_url = detail.get("profile_url") or record.profile_url
    record.headline = detail.get("headline") or record.headline
    if detail.get("display_name"):
        record.display_name = detail["display_name"]
    _note(record, "verification_error", None)
    _note(record, "verified_via", result.via)


def _note(record: ConnectedAccount, key: str, value) -> None:
    """Record operational metadata on the caps blob (no separate table yet)."""
    caps = dict(record.daily_caps or {})
    meta = dict(caps.get("_meta") or {})
    if value is None:
        meta.pop(key, None)
    else:
        meta[key] = value
    caps["_meta"] = meta
    record.daily_caps = caps


def set_status(record: ConnectedAccount, new_status: str) -> None:
    """
    Change an account's status and stamp when it happened.

    ``updated_at`` bumps on *any* write to the row, so it can't answer "how
    long has this account been broken?" This stamp is the thing the run-status
    view reads to say "session expired 2 hours ago" instead of guessing from a
    column that moves for unrelated reasons.
    """
    if record.status != new_status:
        record.status = new_status
        _note(record, "status_changed_at", datetime.now(timezone.utc).isoformat())


async def record_run_outcome(
    db: AsyncSession, record: ConnectedAccount, *, errors: Optional[dict] = None
) -> None:
    """
    Persist what happened the last time the scheduler touched this account.

    Called once per account per tick, whether the tick succeeded or not — a
    scheduler that goes quiet for days looks identical to one that is merely
    idle unless every pass it makes leaves a mark. ``errors`` is the
    ``AccountOutcome.errors`` dict from ``scheduler.tick``: at most one stage
    fails loudest, so only the first is kept as the headline error.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    _note(record, "last_run_at", now_iso)
    if errors:
        stage, message = next(iter(errors.items()))
        _note(record, "last_error", f"{stage}: {message}")
        _note(record, "last_error_at", now_iso)
        _note(record, "last_run_ok", False)
    else:
        _note(record, "last_run_ok", True)
    await db.commit()


async def update_account(
    db: AsyncSession, record: ConnectedAccount, payload
) -> ConnectedAccount:
    """Apply a partial policy update."""
    if payload.mode is not None:
        if payload.mode not in (
            EngagementMode.OUTREACH,
            EngagementMode.ACCOUNT_BASED_ENGAGEMENT,
        ):
            raise AccountError(f"unknown mode: {payload.mode}")
        record.mode = payload.mode
    if payload.status is not None:
        set_status(record, payload.status)
    if payload.display_name is not None:
        record.display_name = payload.display_name
    if payload.active_icp_id is not None:
        record.active_icp_id = uuid.UUID(str(payload.active_icp_id))
    if payload.daily_caps is not None:
        merged = dict(record.daily_caps or {})
        merged.update(payload.daily_caps)
        record.daily_caps = merged

    await db.commit()
    await db.refresh(record)
    return record


async def disconnect_account(db: AsyncSession, record: ConnectedAccount) -> None:
    """
    Soft-delete the account and destroy its stored credentials.

    Soft delete keeps the outreach history (who was contacted, when) intact for
    audit and suppression purposes; the credentials are hard-deleted because
    there is no reason to retain a bearer token past disconnection.
    """
    record.auth_blob = None
    set_status(record, AccountStatus.INACTIVE)
    record.deleted_at = datetime.now(timezone.utc)
    await db.commit()


async def check_health(
    db: AsyncSession, record: ConnectedAccount, transport: Any = None
) -> dict:
    """Re-verify a connected account's session right now."""
    live = LiveAccount(record, decrypt_auth(record.auth_blob))
    if not live.auth_blob:
        set_status(record, AccountStatus.AUTH_REQUIRED)
        await db.commit()
        return {
            "account_id": str(record.id),
            "ok": False,
            "status": record.status,
            "error": "no credentials stored",
        }

    try:
        result = await _transport_for(live, transport).whoami(live)
    except TransportError as exc:
        set_status(record, AccountStatus.AUTH_REQUIRED)
        await db.commit()
        return {
            "account_id": str(record.id),
            "ok": False,
            "status": record.status,
            "error": str(exc),
        }

    set_status(record, AccountStatus.ACTIVE if result.success else AccountStatus.AUTH_REQUIRED)
    await db.commit()
    return {
        "account_id": str(record.id),
        "ok": bool(result.success),
        "status": record.status,
        "detail": result.detail,
        "error": result.error,
    }


def to_response(record: ConnectedAccount) -> AccountResponse:
    """Serialize an account, deliberately omitting all auth material."""
    meta = (record.daily_caps or {}).get("_meta") or {}
    return AccountResponse(
        id=str(record.id),
        org_id=str(record.org_id),
        user_id=str(record.user_id),
        status=record.status,
        mode=record.mode,
        display_name=record.display_name,
        headline=record.headline,
        profile_url=record.profile_url,
        linkedin_member_urn=record.linkedin_member_urn,
        active_icp_id=str(record.active_icp_id) if record.active_icp_id else None,
        policy=caps_policy.describe(record),
        has_credentials=bool(record.auth_blob),
        transport=meta.get("verified_via"),
        last_post_at=record.last_post_at,
        last_active_at=record.last_active_at,
        created_at=record.created_at,
        status_since=meta.get("status_changed_at"),
        last_run_at=meta.get("last_run_at"),
        last_run_ok=meta.get("last_run_ok"),
        last_error=meta.get("last_error"),
        last_error_at=meta.get("last_error_at"),
    )

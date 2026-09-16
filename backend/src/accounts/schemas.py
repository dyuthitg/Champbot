"""Pydantic schemas for the connected-account API."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from src.accounts.models import EngagementMode


class AccountConnect(BaseModel):
    """
    Request to connect a LinkedIn identity.

    The session cookie is captured from a browser the user is already logged
    into. We deliberately do NOT accept a LinkedIn password: storing one would
    make this system a credential honeypot, and a cookie can be revoked by the
    user at any time by signing out of that session.
    """

    li_at: str = Field(..., min_length=20, description="The li_at session cookie value")
    jsessionid: Optional[str] = Field(
        None, description="JSESSIONID cookie value; required for write actions (CSRF)"
    )
    label: Optional[str] = Field(None, max_length=255, description="Friendly name")
    mode: str = Field(
        default=EngagementMode.OUTREACH,
        description="outreach | account_based_engagement",
    )
    proxy_url: Optional[str] = Field(
        None, description="Per-account egress proxy, strongly recommended at scale"
    )
    timezone: Optional[str] = Field(None, description="IANA tz for the activity window")


class AccountUpdate(BaseModel):
    """Partial update of an account's engagement policy."""

    mode: Optional[str] = None
    status: Optional[str] = None
    active_icp_id: Optional[str] = None
    daily_caps: Optional[dict] = None
    display_name: Optional[str] = None


class AccountRotateAuth(BaseModel):
    """Replace expired session cookies without recreating the account."""

    li_at: str = Field(..., min_length=20)
    jsessionid: Optional[str] = None


class AccountResponse(BaseModel):
    """
    An account as returned by the API.

    Note the absence of any auth field: credentials are write-only and never
    leave the server.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    user_id: str
    status: str
    mode: Optional[str] = None
    display_name: Optional[str] = None
    headline: Optional[str] = None
    profile_url: Optional[str] = None
    linkedin_member_urn: Optional[str] = None
    active_icp_id: Optional[str] = None
    policy: dict = Field(default_factory=dict, description="Effective caps + pacing")
    has_credentials: bool = False
    transport: Optional[str] = Field(
        None, description="Which transport verified this account: mobile | playwright"
    )
    last_post_at: Optional[datetime] = None
    last_active_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    # Run-status fields: what someone checks to know the bot is alive.
    status_since: Optional[datetime] = Field(
        None, description="When the current status started (e.g. when the session expired)"
    )
    last_run_at: Optional[datetime] = Field(
        None, description="When the scheduler last swept this account"
    )
    last_run_ok: Optional[bool] = Field(
        None, description="Whether that last sweep completed with no stage errors"
    )
    last_error: Optional[str] = Field(
        None, description="The most recent stage error, e.g. 'send: TransportError: ...'"
    )
    last_error_at: Optional[datetime] = None


class AccountListResponse(BaseModel):
    accounts: list[AccountResponse]
    total: int


class AccountHealth(BaseModel):
    """Live verification result for one account."""

    account_id: str
    ok: bool
    status: str
    detail: Optional[dict] = None
    error: Optional[str] = None

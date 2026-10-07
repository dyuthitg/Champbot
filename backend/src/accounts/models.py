"""
ConnectedAccount model: a LinkedIn identity the system acts *as* on behalf of a
user. This replaces the ad-hoc ``account_ids`` string lists with a real,
per-user, per-org entity carrying auth material, device fingerprint, per-account
caps, engagement mode, and the "gone quiet" signal used for autonomous posting.

Cross-dialect column types (``Uuid``, ``JSON``) keep it testable on SQLite.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.database.models import Base


class AccountStatus:
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    RATE_LIMITED = "rate_limited"
    AUTH_REQUIRED = "auth_required"
    ERROR = "error"


class EngagementMode:
    """The per-account 'thought process'."""
    OUTREACH = "outreach"
    ACCOUNT_BASED_ENGAGEMENT = "account_based_engagement"


class ConnectedAccount(Base):
    __tablename__ = "connected_accounts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    status: Mapped[str] = mapped_column(String(50), default=AccountStatus.INACTIVE)

    # LinkedIn identity
    linkedin_member_urn: Mapped[Optional[str]] = mapped_column(String(255))
    profile_url: Mapped[Optional[str]] = mapped_column(String(512))
    display_name: Mapped[Optional[str]] = mapped_column(String(255))
    headline: Mapped[Optional[str]] = mapped_column(Text)

    # Auth material (cookies / li_at / session), Fernet-encrypted at rest.
    auth_blob: Mapped[Optional[str]] = mapped_column(Text)

    # Per-account device fingerprint for the mobile transport (user-agent,
    # device id, carrier headers, TLS impersonation profile).
    device_fingerprint: Mapped[Optional[dict]] = mapped_column(JSON)
    proxy: Mapped[Optional[dict]] = mapped_column(JSON)

    # Per-action hourly/daily cap overrides; defaults come from LinkedInConfig.
    daily_caps: Mapped[Optional[dict]] = mapped_column(JSON)

    # Engagement direction and active ICP (FK added when ICP models land).
    mode: Mapped[Optional[str]] = mapped_column(String(64))
    active_icp_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)

    # "Gone quiet" signal driving autonomous posting.
    last_post_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

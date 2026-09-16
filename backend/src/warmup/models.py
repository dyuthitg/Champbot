"""
Account activity ledger.

Every action an account performs — a like during warm-up, an invitation, a
follow-up message — is written here. Three things depend on it:

- **Warm-up graduation.** Stages require cumulative work ("30 likes, 8
  comments"), and Redis rate-limit counters expire after a week, so they can't
  answer "has this account done enough yet".
- **The funnel.** Invitations sent → accepted → replied → booked is computed
  from this ledger joined against target state.
- **The learning harness.** Each row can carry the ``variant`` used, so the
  system can tell which angle actually gets accepted and replied to.

It is also the audit trail: if an account gets restricted, this is the record
of exactly what it did and when.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.database.models import Base


class ActivityStatus:
    OK = "ok"
    FAILED = "failed"
    BLOCKED = "blocked"


class AccountActivity(Base):
    """One thing an account did (or tried to do)."""

    __tablename__ = "account_activity"
    __table_args__ = (
        Index("ix_activity_account_action", "account_id", "action"),
        Index("ix_activity_account_time", "account_id", "created_at"),
        Index("ix_activity_variant", "account_id", "variant"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("connected_accounts.id", ondelete="CASCADE"), nullable=False
    )

    action: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=ActivityStatus.OK)

    # Which warm-up stage the account was in when this happened. Makes the
    # ramp auditable after the fact.
    stage: Mapped[Optional[str]] = mapped_column(String(32))

    # What it acted on, and who it was aimed at (when there is a target).
    subject_urn: Mapped[Optional[str]] = mapped_column(String(255))
    target_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, index=True)

    # The copy/angle variant used, for outcome attribution.
    variant: Mapped[Optional[str]] = mapped_column(String(64))

    detail: Mapped[Optional[dict]] = mapped_column(JSON)
    error: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

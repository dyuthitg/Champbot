"""
Outreach suggestions: the unit of human review.

Nothing is ever sent to LinkedIn directly from the targeting layer. Every
outbound action first becomes a ``OutreachSuggestion`` — a proposed action
toward one person, with the drafted copy, the relevance score, and the
rationale — which a human approves, edits, or rejects. Approval is what
converts it into something the executor may send.

That indirection is the product's central safety property. It means the worst
possible failure of the targeting or copywriting layer is a bad *suggestion*
sitting in a queue, not a bad message in a stranger's inbox.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.database.models import Base


class SuggestionAction:
    CONNECT = "connect"
    MESSAGE = "message"
    COMMENT = "comment"
    LIKE = "like"
    FOLLOW = "follow"


class SuggestionStatus:
    PENDING = "pending"        # awaiting the user
    APPROVED = "approved"      # user said yes; queued for paced execution
    SCHEDULED = "scheduled"    # has a send time
    SENT = "sent"              # executed successfully
    FAILED = "failed"          # execution failed
    REJECTED = "rejected"      # user said no
    EXPIRED = "expired"        # sat unreviewed too long to still be timely
    BLOCKED = "blocked"        # a safety gate refused it
    CANCELLED = "cancelled"    # withdrawn because the prospect replied


class OutreachSuggestion(Base):
    """One proposed action toward one person, pending human judgement."""

    __tablename__ = "outreach_suggestions"
    __table_args__ = (
        # The dedupe backbone: at most one live suggestion of a given action
        # per target. Enforced again in the service layer for terminal states.
        Index("ix_suggestion_target_action", "target_id", "action"),
        Index("ix_suggestion_account_status", "account_id", "status"),
        Index("ix_suggestion_due", "status", "scheduled_for"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("connected_accounts.id", ondelete="CASCADE"), nullable=False
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("outreach_targets.id", ondelete="CASCADE"), nullable=False
    )

    action: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=SuggestionStatus.PENDING, index=True
    )

    # What we propose to send. ``final_text`` is what actually goes out: the
    # user's edit if they made one, otherwise the draft.
    draft_text: Mapped[Optional[str]] = mapped_column(Text)
    final_text: Mapped[Optional[str]] = mapped_column(Text)

    # Why we are suggesting this, in the user's language.
    rationale: Mapped[Optional[str]] = mapped_column(Text)
    relevance_score: Mapped[int] = mapped_column(Integer, default=0)
    relevance_reasons: Mapped[Optional[list]] = mapped_column(JSON)

    # Output of the deterministic copy quality gate.
    quality_score: Mapped[Optional[int]] = mapped_column(Integer)
    quality_warnings: Mapped[Optional[list]] = mapped_column(JSON)

    # Which subject/activity this action attaches to (a post urn, for
    # comment/like), and how the copy was produced (model or template).
    subject_urn: Mapped[Optional[str]] = mapped_column(String(255))
    generated_by: Mapped[Optional[str]] = mapped_column(String(128))

    # Which cadence step produced this, and which copy variant was used --
    # together these let outcomes be attributed back to what was actually tried.
    step: Mapped[Optional[str]] = mapped_column(String(32))
    variant: Mapped[Optional[str]] = mapped_column(String(64))

    # Sequencing: a follow-up message that must wait for an invitation to be
    # accepted points at the suggestion that created the invitation.
    depends_on_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    not_before: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    scheduled_for: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)

    result: Mapped[Optional[dict]] = mapped_column(JSON)
    error: Mapped[Optional[str]] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

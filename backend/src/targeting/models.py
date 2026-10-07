"""
Targeting models: who an account is trying to reach, and who it has found.

``ICPProfile`` is the definition of the right person — the thing that turns
"send 500 invitations" into "talk to the twenty people this actually matters
to". ``OutreachTarget`` is one concrete prospect, carrying the relevance score
and the human-readable reasons behind it so the user reviewing a suggestion can
see *why* this person was surfaced.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.database.models import Base


class TargetStatus:
    """
    Lifecycle of a prospect for one account.

    The order matters: everything from CONNECTED onward implies the invitation
    was accepted, and everything from REPLIED onward implies they wrote back.
    The funnel and the acceptance governor both rely on that being true.
    """
    NEW = "new"                 # imported, not yet evaluated
    SCORED = "scored"           # relevance computed
    SUGGESTED = "suggested"     # a suggestion exists awaiting the user
    APPROVED = "approved"       # user approved an action toward them
    CONTACTED = "contacted"     # an invitation/message was actually sent
    CONNECTED = "connected"     # invitation accepted
    REPLIED = "replied"         # they wrote back -- sequence pauses here
    INTERESTED = "interested"   # qualified as a real opportunity
    BOOKED = "booked"           # meeting on the calendar
    NOT_INTERESTED = "not_interested"
    SKIPPED = "skipped"         # below the relevance floor / excluded
    SUPPRESSED = "suppressed"   # never contact (user decision or opt-out)


# Once a target reaches one of these, automation stops touching them: a human
# is in the conversation, and the worst thing the system can do is talk over it.
HUMAN_OWNED = (
    TargetStatus.REPLIED,
    TargetStatus.INTERESTED,
    TargetStatus.BOOKED,
    TargetStatus.NOT_INTERESTED,
    TargetStatus.SUPPRESSED,
)


class ICPProfile(Base):
    """The definition of a good-fit person for one account."""

    __tablename__ = "icp_profiles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("connected_accounts.id", ondelete="CASCADE"), index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Matching criteria. Lists of plain strings, matched case-insensitively.
    titles: Mapped[Optional[list]] = mapped_column(JSON)
    seniorities: Mapped[Optional[list]] = mapped_column(JSON)
    industries: Mapped[Optional[list]] = mapped_column(JSON)
    keywords: Mapped[Optional[list]] = mapped_column(JSON)
    excluded_keywords: Mapped[Optional[list]] = mapped_column(JSON)
    excluded_titles: Mapped[Optional[list]] = mapped_column(JSON)
    locations: Mapped[Optional[list]] = mapped_column(JSON)
    company_sizes: Mapped[Optional[list]] = mapped_column(JSON)

    # What the user is actually offering / why they're reaching out. This is the
    # single most important input to non-generic copy.
    value_proposition: Mapped[Optional[str]] = mapped_column(Text)
    # Free-text steering from the user ("mention we met at SaaStr", "never
    # pitch in the first message"). Fed verbatim into the copywriter.
    instructions: Mapped[Optional[str]] = mapped_column(Text)

    # Which brand voice (src/outreach/brand_voice.py, config/brand_voices/*.yaml)
    # to write in. Not a foreign key -- profiles live as files, not rows, so a
    # marketer can add one without touching the database. Null means the
    # product's default, brand-neutral voice.
    brand_voice_id: Mapped[Optional[str]] = mapped_column(String(64))

    # Suggestions below this score are never shown.
    relevance_floor: Mapped[int] = mapped_column(Integer, default=60)

    is_active: Mapped[bool] = mapped_column(default=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OutreachTarget(Base):
    """One prospect, scoped to the account that will reach out to them."""

    __tablename__ = "outreach_targets"
    __table_args__ = (
        # One row per person per account: the foundation of "never touch the
        # same person twice".
        Index("ix_target_account_member", "account_id", "member_urn", unique=True),
        Index("ix_target_account_status", "account_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("connected_accounts.id", ondelete="CASCADE"), nullable=False
    )
    icp_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)

    # Identity. member_urn is the stable key; public_id is the /in/ handle.
    member_urn: Mapped[str] = mapped_column(String(255), nullable=False)
    public_id: Mapped[Optional[str]] = mapped_column(String(255))
    profile_url: Mapped[Optional[str]] = mapped_column(String(512))

    full_name: Mapped[Optional[str]] = mapped_column(String(255))
    first_name: Mapped[Optional[str]] = mapped_column(String(128))
    headline: Mapped[Optional[str]] = mapped_column(Text)
    title: Mapped[Optional[str]] = mapped_column(String(255))
    company: Mapped[Optional[str]] = mapped_column(String(255))
    industry: Mapped[Optional[str]] = mapped_column(String(255))
    location: Mapped[Optional[str]] = mapped_column(String(255))

    # Where this person came from: whatsapp_link | post_engagement | csv | manual
    source: Mapped[Optional[str]] = mapped_column(String(64))
    source_ref: Mapped[Optional[str]] = mapped_column(String(512))
    # Something specific and true about them, used to personalize copy: a recent
    # post, a shared group, how we found them.
    context: Mapped[Optional[dict]] = mapped_column(JSON)

    relevance_score: Mapped[int] = mapped_column(Integer, default=0)
    relevance_reasons: Mapped[Optional[list]] = mapped_column(JSON)

    status: Mapped[str] = mapped_column(String(32), default=TargetStatus.NEW, index=True)
    last_touched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Funnel timestamps. Kept explicitly rather than inferred from status so
    # the acceptance and reply rates survive later status changes.
    invited_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    replied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    booked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Which copy/angle variant was used on this person, for outcome attribution.
    variant: Mapped[Optional[str]] = mapped_column(String(64))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

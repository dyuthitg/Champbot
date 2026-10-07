"""
Tenancy models: Organization and User.

The system is a central multi-tenant SaaS: team members authenticate via Clerk,
belong to an Organization, and connect their own LinkedIn accounts. These models
are the tenancy spine every other entity (ConnectedAccount, ICP, campaigns, ...)
scopes to.

Cross-dialect column types (``Uuid``, ``JSON``) are used so the tables round-trip
on both Postgres (production) and SQLite (tests).
"""

import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.database.models import Base


class UserRole:
    """Role constants (stored as strings for cross-dialect simplicity)."""
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class Organization(Base):
    """A tenant. Maps to a Clerk organization, or a personal workspace."""
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Null for a personal workspace (a Clerk user with no active org).
    clerk_org_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    plan: Mapped[str] = mapped_column(String(50), default="free")

    # Admin WhatsApp number whose group link-scans fan out to this org's bots.
    whatsapp_admin_number: Mapped[Optional[str]] = mapped_column(String(64))

    # Org-level settings (default OpenRouter model slots, timezone, ...).
    settings: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    users: Mapped[List["User"]] = relationship(back_populates="organization")


class User(Base):
    """A team member, identified by their Clerk user id, scoped to an org."""
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    clerk_user_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[Optional[str]] = mapped_column(String(320))
    display_name: Mapped[Optional[str]] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default=UserRole.MEMBER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    organization: Mapped["Organization"] = relationship(back_populates="users")

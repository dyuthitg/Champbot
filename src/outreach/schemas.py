"""Pydantic schemas for the suggestion review queue."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class GenerateRequest(BaseModel):
    """Ask the engine to build a review queue for one account."""

    account_id: str
    icp_id: Optional[str] = None
    limit: Optional[int] = Field(
        None, ge=1, le=50, description="Cap on suggestions this run (defaults to the daily budget)"
    )


class TargetSummary(BaseModel):
    """Just enough about the person for the reviewer to make a judgement."""

    id: str
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    headline: Optional[str] = None
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    profile_url: Optional[str] = None
    status: Optional[str] = None


class SuggestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    account_id: str
    target_id: str
    action: str
    status: str
    draft_text: Optional[str] = None
    final_text: Optional[str] = None
    rationale: Optional[str] = None
    relevance_score: int = 0
    relevance_reasons: List[str] = Field(default_factory=list)
    quality_score: Optional[int] = None
    quality_warnings: List[str] = Field(default_factory=list)
    generated_by: Optional[str] = None
    subject_urn: Optional[str] = None
    scheduled_for: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    error: Optional[str] = None
    created_at: Optional[datetime] = None
    target: Optional[TargetSummary] = None
    # Names of other pending suggestions (same action) this draft reads like
    # -- see src/outreach/similarity.py. Empty when nothing else queued is
    # close enough to flag.
    similar_to: List[str] = Field(default_factory=list)


class SuggestionListResponse(BaseModel):
    suggestions: List[SuggestionResponse]
    total: int


class GenerateResponse(BaseModel):
    """
    Result of a generation run.

    ``skipped`` and ``message`` are the honesty surface: they explain who was
    considered and why most people didn't make the cut.
    """

    created: List[SuggestionResponse]
    considered: int
    skipped: dict = Field(default_factory=dict)
    message: str


class ApproveRequest(BaseModel):
    edited_text: Optional[str] = Field(
        None, description="Replaces the draft; re-checked by the quality gate"
    )
    send_at: Optional[datetime] = Field(
        None, description="Override the paced send time"
    )


class RejectRequest(BaseModel):
    suppress_target: bool = Field(
        False, description="Also block this person from all future suggestions"
    )
    reason: Optional[str] = None


class RunDueResponse(BaseModel):
    """Result of executing everything currently due for an account."""

    sent: List[str]
    blocked: dict = Field(default_factory=dict)
    considered: int


class ActivityItem(BaseModel):
    """One line in the account activity feed."""

    id: str
    account_id: str
    action: str
    status: str
    target_name: Optional[str] = None
    target_headline: Optional[str] = None
    text: Optional[str] = None
    relevance_score: int = 0
    occurred_at: Optional[datetime] = None
    error: Optional[str] = None


class ActivityResponse(BaseModel):
    items: List[ActivityItem]
    total: int


class AccountStats(BaseModel):
    """Per-account roll-up for the admin dashboard."""

    account_id: str
    display_name: Optional[str] = None
    status: str
    mode: Optional[str] = None
    pending_review: int = 0
    scheduled: int = 0
    sent_today: int = 0
    sent_total: int = 0
    failed: int = 0
    connects_sent: int = 0
    messages_sent: int = 0
    remaining_today: dict = Field(default_factory=dict)

    # Where this account is in the warm-up programme, and what its measured
    # outcomes say about whether it is safe to keep going.
    warmup_stage: Optional[str] = None
    warmup_stage_name: Optional[str] = None
    warmup_paused: bool = False
    health_verdict: str = "unknown"
    health_headline: str = ""
    throttle: float = 1.0
    funnel: dict = Field(default_factory=dict)


class DashboardResponse(BaseModel):
    """Every account in the org at a glance."""

    accounts: List[AccountStats]
    totals: dict = Field(default_factory=dict)

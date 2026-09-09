"""Pydantic schemas for the suggestion review queue."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    # What the suggestion is replying to. An operator can't judge a comment
    # without seeing the post it's a reply to -- this was missing entirely
    # until 2026-09-01; see OutreachTarget.context in src/targeting/models.py.
    post_text: Optional[str] = None
    post_urn: Optional[str] = None


class QualityFlagOut(BaseModel):
    """
    One named guardrail a draft broke.

    The wording is not composed here: ``label`` comes straight from the rule
    table in ``src/outreach/quality.py`` so a rule is called the same thing in
    the spec, in the gate, and on the chip the operator reads. ``code`` is what
    the queue groups and filters by.
    """

    code: str
    label: str
    # blocker (cannot be approved) | warning (costs score) | advisory (shown only)
    severity: str
    detail: str
    # Heading in COMMENT_QUALITY_SPEC_V1.md, or null for a check that runs in
    # the code but was never written into the spec.
    spec_ref: Optional[str] = None


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
    # Every guardrail this draft breaks, named. quality_warnings above stays
    # as it was (free-text sentences, written at generation time); this is the
    # same findings re-checked against the text as it stands now, plus the
    # advisory-only rules, each tagged with the rule it broke so the queue can
    # show a chip and filter by failure type.
    quality_flags: List[QualityFlagOut] = Field(default_factory=list)


class SuggestionListResponse(BaseModel):
    """
    One page of the review queue.

    ``total`` used to be ``len(suggestions)`` -- the size of the page, not the
    size of the queue -- so a screen showing 200 of 400 items had no way to
    know the other 200 existed, and no way to say so. It is now a real count of
    everything matching the filter.
    """

    suggestions: List[SuggestionResponse]
    total: int
    # Where this page started and how many more there are after it. The queue
    # screen needs both to say "showing 50 of 412" and to fetch the next page.
    offset: int = 0
    has_more: bool = False


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
    # Required, not optional -- this is the data that improves the prompt
    # later. A reject with no reason teaches the system nothing.
    reason: str = Field(..., min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def reason_is_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("reason cannot be blank")
        return value


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

    # Run-status: what someone checks at 9am to know the bot is alive.
    caps_today: dict = Field(
        default_factory=dict, description="Per action: {used, cap, week_used, week_cap, tracked}"
    )
    quiet_hours_now: bool = False
    weekend_now: bool = False
    status_since: Optional[datetime] = Field(
        None, description="When the current status started, e.g. when the session expired"
    )
    last_run_at: Optional[datetime] = Field(None, description="When the scheduler last swept this account")
    last_run_ok: Optional[bool] = None
    last_error: Optional[str] = Field(
        None, description="The most recent stage error, e.g. 'send: TransportError: ...'"
    )
    last_error_at: Optional[datetime] = None


class DashboardResponse(BaseModel):
    """Every account in the org at a glance."""

    accounts: List[AccountStats]
    totals: dict = Field(default_factory=dict)

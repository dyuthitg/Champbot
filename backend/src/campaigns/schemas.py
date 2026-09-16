"""
Pydantic schemas for Campaign API request/response validation.
"""

from pydantic import BaseModel, Field, field_validator, HttpUrl
from typing import Optional, List
from datetime import datetime
from enum import Enum
import uuid
import re


class CampaignStatus(str, Enum):
    """Campaign status enum for API responses."""
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CampaignActions(BaseModel):
    """Actions to perform on target URLs."""
    like: bool = True
    comment: bool = False
    share: bool = False
    follow: bool = False
    comment_templates: Optional[List[str]] = Field(
        default=None,
        description="Custom comment templates (uses AI if not provided)"
    )


class CampaignCreate(BaseModel):
    """Request schema for creating a campaign."""
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Campaign name"
    )
    description: Optional[str] = Field(
        default=None,
        description="Campaign description"
    )
    target_urls: List[str] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="LinkedIn URLs to engage with"
    )
    account_ids: List[str] = Field(
        ...,
        min_length=1,
        description="Connected account IDs to use for engagement"
    )
    actions: CampaignActions = Field(
        default_factory=CampaignActions,
        description="Actions to perform"
    )
    priority: int = Field(
        default=1,
        ge=1,
        le=3,
        description="Priority level (1=normal, 2=high, 3=urgent)"
    )
    scheduled_start_at: Optional[datetime] = Field(
        default=None,
        description="Scheduled start time (None = start manually)"
    )

    @field_validator("target_urls")
    @classmethod
    def validate_linkedin_urls(cls, urls: List[str]) -> List[str]:
        """Validate that all URLs are LinkedIn URLs."""
        linkedin_pattern = re.compile(
            r"^https?://(www\.)?linkedin\.com/"
            r"(posts|feed/update|pulse|in|company|groups|events)"
        )
        invalid_urls = []
        for url in urls:
            if not linkedin_pattern.match(url):
                invalid_urls.append(url)

        if invalid_urls:
            raise ValueError(
                f"Invalid LinkedIn URLs: {invalid_urls}. "
                "URLs must be LinkedIn posts, profiles, or company pages."
            )
        return urls


class CampaignUpdate(BaseModel):
    """Request schema for updating a campaign."""
    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=255
    )
    description: Optional[str] = None
    target_urls: Optional[List[str]] = Field(default=None, min_length=1)
    account_ids: Optional[List[str]] = Field(default=None, min_length=1)
    actions: Optional[CampaignActions] = None
    priority: Optional[int] = Field(default=None, ge=1, le=3)
    scheduled_start_at: Optional[datetime] = None

    @field_validator("target_urls")
    @classmethod
    def validate_linkedin_urls(cls, urls: Optional[List[str]]) -> Optional[List[str]]:
        """Validate LinkedIn URLs if provided."""
        if urls is None:
            return None
        linkedin_pattern = re.compile(
            r"^https?://(www\.)?linkedin\.com/"
            r"(posts|feed/update|pulse|in|company|groups|events)"
        )
        invalid_urls = [url for url in urls if not linkedin_pattern.match(url)]
        if invalid_urls:
            raise ValueError(f"Invalid LinkedIn URLs: {invalid_urls}")
        return urls


class CampaignProgress(BaseModel):
    """Campaign execution progress."""
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    pending_tasks: int = 0
    completion_percent: float = 0.0


class CampaignResponse(BaseModel):
    """Response schema for campaign data."""
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    status: CampaignStatus
    target_urls: List[str]
    account_ids: List[str]
    actions: CampaignActions
    priority: int
    progress: CampaignProgress
    scheduled_start_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CampaignListResponse(BaseModel):
    """Response schema for campaign list."""
    campaigns: List[CampaignResponse]
    total: int
    page: int
    page_size: int


class CampaignTaskResponse(BaseModel):
    """Response schema for campaign task."""
    id: uuid.UUID
    campaign_id: uuid.UUID
    orchestrator_task_id: str
    target_url: str
    status: str
    result: Optional[dict] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class StartCampaignResponse(BaseModel):
    """Response when starting a campaign."""
    campaign_id: uuid.UUID
    status: CampaignStatus
    tasks_created: int
    message: str


class IdempotencyResponse(BaseModel):
    """Response for idempotent requests."""
    is_duplicate: bool
    original_response: Optional[dict] = None
    resource_id: Optional[uuid.UUID] = None

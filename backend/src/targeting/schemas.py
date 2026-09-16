"""Pydantic schemas for ICP definitions and prospect targets."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ICPBase(BaseModel):
    """Shared ICP fields."""

    name: str = Field(..., min_length=1, max_length=255)
    titles: List[str] = Field(default_factory=list)
    seniorities: List[str] = Field(default_factory=list)
    industries: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    excluded_keywords: List[str] = Field(default_factory=list)
    excluded_titles: List[str] = Field(default_factory=list)
    locations: List[str] = Field(default_factory=list)
    company_sizes: List[str] = Field(default_factory=list)
    value_proposition: Optional[str] = Field(
        None, description="What you help these people with, in your own words"
    )
    instructions: Optional[str] = Field(
        None,
        description="Standing direction for the copywriter, e.g. 'never pitch "
        "in a first message', 'mention we're both in the RevOps group'",
    )
    brand_voice_id: Optional[str] = Field(
        None,
        description="Which brand voice profile (config/brand_voices/*.yaml) to "
        "write in. Null uses the product's default voice.",
    )
    relevance_floor: int = Field(
        default=60, ge=0, le=100, description="Suggestions below this score are never shown"
    )


class ICPCreate(ICPBase):
    account_id: Optional[str] = None


class ICPUpdate(BaseModel):
    """Partial ICP update; only supplied fields change."""

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    titles: Optional[List[str]] = None
    seniorities: Optional[List[str]] = None
    industries: Optional[List[str]] = None
    keywords: Optional[List[str]] = None
    excluded_keywords: Optional[List[str]] = None
    excluded_titles: Optional[List[str]] = None
    locations: Optional[List[str]] = None
    company_sizes: Optional[List[str]] = None
    value_proposition: Optional[str] = None
    instructions: Optional[str] = None
    brand_voice_id: Optional[str] = None
    relevance_floor: Optional[int] = Field(None, ge=0, le=100)
    is_active: Optional[bool] = None


class ICPResponse(ICPBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    account_id: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None


class BrandVoiceSummary(BaseModel):
    """One brand voice profile, as shown in the picker. Not a database row --
    read straight off config/brand_voices/*.yaml."""

    id: str
    brand_name: str
    formality: str


class TargetImportItem(BaseModel):
    """
    One prospect to import.

    Either ``profile_url`` or ``member_urn`` identifies the person; the rest is
    the context that makes personalized copy possible. The more of it supplied,
    the less generic the resulting message.
    """

    profile_url: Optional[str] = None
    member_urn: Optional[str] = None
    public_id: Optional[str] = None
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    headline: Optional[str] = None
    title: Optional[str] = None
    company: Optional[str] = None
    industry: Optional[str] = None
    location: Optional[str] = None
    source: Optional[str] = Field(None, description="csv | manual | whatsapp_link | post_engagement")
    source_ref: Optional[str] = None
    context: Optional[dict] = Field(
        None,
        description="Grounding facts for the copywriter: post_urn, post_text, "
        "how_found, shared_group",
    )


class TargetImportRequest(BaseModel):
    account_id: str
    icp_id: Optional[str] = None
    targets: List[TargetImportItem] = Field(..., min_length=1, max_length=500)


class TargetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    account_id: str
    member_urn: str
    public_id: Optional[str] = None
    profile_url: Optional[str] = None
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    headline: Optional[str] = None
    title: Optional[str] = None
    company: Optional[str] = None
    industry: Optional[str] = None
    location: Optional[str] = None
    source: Optional[str] = None
    relevance_score: int = 0
    relevance_reasons: List[str] = Field(default_factory=list)
    status: str
    last_touched_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class TargetListResponse(BaseModel):
    targets: List[TargetResponse]
    total: int


class TargetImportResponse(BaseModel):
    imported: int
    duplicates: int
    scored: int
    targets: List[TargetResponse]


class ScorePreviewRequest(BaseModel):
    """Dry-run an ICP against a hypothetical person before committing to it."""

    icp: ICPBase
    target: TargetImportItem


class ScorePreviewResponse(BaseModel):
    score: int
    reasons: List[str]
    excluded: bool
    exclusion_reason: Optional[str] = None
    passes_floor: bool

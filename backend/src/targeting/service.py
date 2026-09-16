"""ICP and target persistence."""

from __future__ import annotations

import re
import uuid
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.targeting.models import ICPProfile, OutreachTarget, TargetStatus
from src.targeting.schemas import ICPResponse, TargetResponse
from src.targeting.scoring import score_target

_PROFILE_URL = re.compile(r"linkedin\.com/in/([^/?#]+)", re.I)

_ICP_LIST_FIELDS = (
    "titles",
    "seniorities",
    "industries",
    "keywords",
    "excluded_keywords",
    "excluded_titles",
    "locations",
    "company_sizes",
)


def public_id_from_url(url: Optional[str]) -> Optional[str]:
    """Extract the ``/in/<handle>`` identifier from a LinkedIn profile URL."""
    if not url:
        return None
    match = _PROFILE_URL.search(str(url))
    return match.group(1).rstrip("/") if match else None


# ----------------------------------------------------------------------
# ICP
# ----------------------------------------------------------------------


async def create_icp(db: AsyncSession, org_id: str, payload) -> ICPProfile:
    icp = ICPProfile(
        id=uuid.uuid4(),
        org_id=uuid.UUID(str(org_id)),
        account_id=uuid.UUID(str(payload.account_id)) if payload.account_id else None,
        name=payload.name,
        value_proposition=payload.value_proposition,
        instructions=payload.instructions,
        brand_voice_id=payload.brand_voice_id,
        relevance_floor=payload.relevance_floor,
    )
    for field in _ICP_LIST_FIELDS:
        setattr(icp, field, getattr(payload, field, None) or [])
    db.add(icp)
    await db.commit()
    await db.refresh(icp)
    return icp


async def list_icps(db: AsyncSession, org_id: str) -> List[ICPProfile]:
    stmt = (
        select(ICPProfile)
        .where(
            ICPProfile.org_id == uuid.UUID(str(org_id)),
            ICPProfile.deleted_at.is_(None),
        )
        .order_by(ICPProfile.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def get_icp(db: AsyncSession, icp_id: str, org_id: str) -> Optional[ICPProfile]:
    try:
        key = uuid.UUID(str(icp_id))
    except (ValueError, TypeError):
        return None
    stmt = select(ICPProfile).where(
        ICPProfile.id == key,
        ICPProfile.org_id == uuid.UUID(str(org_id)),
        ICPProfile.deleted_at.is_(None),
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def update_icp(db: AsyncSession, icp: ICPProfile, payload) -> ICPProfile:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(icp, field, value)
    await db.commit()
    await db.refresh(icp)
    return icp


async def delete_icp(db: AsyncSession, icp: ICPProfile) -> None:
    from datetime import datetime, timezone

    icp.deleted_at = datetime.now(timezone.utc)
    icp.is_active = False
    await db.commit()


# ----------------------------------------------------------------------
# Targets
# ----------------------------------------------------------------------


async def import_targets(
    db: AsyncSession,
    *,
    org_id: str,
    account_id: str,
    items,
    icp: Optional[ICPProfile] = None,
) -> Tuple[List[OutreachTarget], int]:
    """
    Import prospects for an account, skipping anyone already on file.

    Duplicate handling is silent and by design: re-uploading the same list must
    never produce a second round of outreach to the same people.
    """
    account_key = uuid.UUID(str(account_id))

    existing = set(
        (
            await db.execute(
                select(OutreachTarget.member_urn).where(
                    OutreachTarget.account_id == account_key
                )
            )
        )
        .scalars()
        .all()
    )

    created: List[OutreachTarget] = []
    duplicates = 0

    for item in items:
        public_id = item.public_id or public_id_from_url(item.profile_url)
        member_urn = item.member_urn or public_id
        if not member_urn:
            duplicates += 1  # nothing identifies this person; skip it
            continue
        if member_urn in existing:
            duplicates += 1
            continue
        existing.add(member_urn)

        first_name = item.first_name
        if not first_name and item.full_name:
            first_name = str(item.full_name).split()[0]

        target = OutreachTarget(
            id=uuid.uuid4(),
            org_id=uuid.UUID(str(org_id)),
            account_id=account_key,
            icp_id=icp.id if icp else None,
            member_urn=member_urn,
            public_id=public_id,
            profile_url=item.profile_url
            or (f"https://www.linkedin.com/in/{public_id}" if public_id else None),
            full_name=item.full_name,
            first_name=first_name,
            headline=item.headline,
            title=item.title,
            company=item.company,
            industry=item.industry,
            location=item.location,
            source=item.source or "manual",
            source_ref=item.source_ref,
            context=item.context,
            status=TargetStatus.NEW,
        )

        if icp is not None:
            result = score_target(target, icp)
            target.relevance_score = result.score
            target.relevance_reasons = result.reasons
            target.status = (
                TargetStatus.SKIPPED if result.excluded else TargetStatus.SCORED
            )

        db.add(target)
        created.append(target)

    await db.commit()
    for target in created:
        await db.refresh(target)
    return created, duplicates


async def list_targets(
    db: AsyncSession,
    *,
    org_id: str,
    account_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
) -> List[OutreachTarget]:
    stmt = select(OutreachTarget).where(
        OutreachTarget.org_id == uuid.UUID(str(org_id))
    )
    if account_id:
        stmt = stmt.where(OutreachTarget.account_id == uuid.UUID(str(account_id)))
    if status:
        stmt = stmt.where(OutreachTarget.status == status)
    stmt = stmt.order_by(OutreachTarget.relevance_score.desc()).limit(limit)
    return list((await db.execute(stmt)).scalars().all())


async def suppress_target(db: AsyncSession, target: OutreachTarget) -> OutreachTarget:
    """Put a person permanently out of reach of all future outreach."""
    target.status = TargetStatus.SUPPRESSED
    await db.commit()
    await db.refresh(target)
    return target


# ----------------------------------------------------------------------
# Serialization
# ----------------------------------------------------------------------


def icp_to_response(icp: ICPProfile) -> ICPResponse:
    return ICPResponse(
        id=str(icp.id),
        org_id=str(icp.org_id),
        account_id=str(icp.account_id) if icp.account_id else None,
        name=icp.name,
        titles=icp.titles or [],
        seniorities=icp.seniorities or [],
        industries=icp.industries or [],
        keywords=icp.keywords or [],
        excluded_keywords=icp.excluded_keywords or [],
        excluded_titles=icp.excluded_titles or [],
        locations=icp.locations or [],
        company_sizes=icp.company_sizes or [],
        value_proposition=icp.value_proposition,
        instructions=icp.instructions,
        brand_voice_id=icp.brand_voice_id,
        relevance_floor=icp.relevance_floor,
        is_active=icp.is_active,
        created_at=icp.created_at,
    )


def target_to_response(target: OutreachTarget) -> TargetResponse:
    return TargetResponse(
        id=str(target.id),
        account_id=str(target.account_id),
        member_urn=target.member_urn,
        public_id=target.public_id,
        profile_url=target.profile_url,
        full_name=target.full_name,
        first_name=target.first_name,
        headline=target.headline,
        title=target.title,
        company=target.company,
        industry=target.industry,
        location=target.location,
        source=target.source,
        relevance_score=target.relevance_score or 0,
        relevance_reasons=target.relevance_reasons or [],
        status=target.status,
        last_touched_at=target.last_touched_at,
        created_at=target.created_at,
    )

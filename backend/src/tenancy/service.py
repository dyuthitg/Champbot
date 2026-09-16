"""
Tenancy service: resolve/JIT-provision Organization + User from Clerk claims.

On first sight of a Clerk user we create the local User (and its Organization —
either the Clerk org, or a personal workspace when the token carries no org).
Subsequent requests resolve the existing rows and keep the org membership in
sync with the token.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.tenancy.models import Organization, User, UserRole


async def _get_or_create_org(
    db: AsyncSession, clerk_org_id: Optional[str], name: str
) -> Organization:
    if clerk_org_id:
        row = (
            await db.execute(
                select(Organization).where(Organization.clerk_org_id == clerk_org_id)
            )
        ).scalar_one_or_none()
        if row:
            return row
    org = Organization(clerk_org_id=clerk_org_id, name=name)
    db.add(org)
    await db.flush()
    return org


def _claim(claims: dict, *keys: str) -> Optional[str]:
    for k in keys:
        if claims.get(k):
            return claims[k]
    return None


async def resolve_context(db: AsyncSession, claims: dict):
    """
    Resolve a :class:`RequestContext` from verified Clerk claims, provisioning
    the Organization + User as needed.
    """
    # Imported here to avoid a circular import with the middleware module.
    from src.api.middleware.clerk import RequestContext

    clerk_user_id = _claim(claims, "sub", "user_id")
    if not clerk_user_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="Token missing subject")

    # Clerk commonly puts the active org under 'org_id' / 'o.id'.
    clerk_org_id = _claim(claims, "org_id")
    if not clerk_org_id and isinstance(claims.get("o"), dict):
        clerk_org_id = claims["o"].get("id")
    email = _claim(claims, "email", "email_address")
    role = _claim(claims, "org_role") or UserRole.MEMBER

    user = (
        await db.execute(select(User).where(User.clerk_user_id == clerk_user_id))
    ).scalar_one_or_none()

    if user is None:
        org_name = (
            f"Org {clerk_org_id}" if clerk_org_id else (email or f"user-{clerk_user_id[:8]}")
        )
        org = await _get_or_create_org(db, clerk_org_id, org_name)
        user = User(
            clerk_user_id=clerk_user_id,
            org_id=org.id,
            email=email,
            role=UserRole.OWNER if not clerk_org_id else role,
        )
        db.add(user)
        await db.flush()
    else:
        org = (
            await db.execute(select(Organization).where(Organization.id == user.org_id))
        ).scalar_one()
        # Keep membership in sync if the token's active org changed.
        if clerk_org_id and org.clerk_org_id != clerk_org_id:
            org = await _get_or_create_org(db, clerk_org_id, f"Org {clerk_org_id}")
            user.org_id = org.id
            await db.flush()

    await db.commit()

    return RequestContext(
        user_id=str(user.id),
        org_id=str(user.org_id),
        clerk_user_id=clerk_user_id,
        clerk_org_id=clerk_org_id,
        email=email,
        role=user.role,
    )

"""
Identity route.

``GET /api/v1/me`` authenticates via Clerk and returns the resolved tenancy
context, JIT-provisioning the Organization + User on first call. This is the
smallest authenticated surface that exercises the full auth + tenancy path.
"""

from fastapi import APIRouter, Depends

from src.api.middleware.clerk import RequestContext, get_request_context

router = APIRouter(tags=["identity"])


@router.get("/me")
async def get_me(ctx: RequestContext = Depends(get_request_context)) -> dict:
    """Return the authenticated user's tenancy context."""
    return {
        "user_id": ctx.user_id,
        "org_id": ctx.org_id,
        "clerk_user_id": ctx.clerk_user_id,
        "clerk_org_id": ctx.clerk_org_id,
        "email": ctx.email,
        "role": ctx.role,
    }

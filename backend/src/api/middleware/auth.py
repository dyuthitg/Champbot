"""
Authentication (Clerk).

This module previously targeted Supabase and imported a non-existent
``supabase_client``. Auth is now handled by Clerk; these names are kept as thin
re-exports so any existing imports keep working.
"""

from src.api.middleware.clerk import (  # noqa: F401
    RequestContext,
    get_current_org_id,
    get_request_context,
)

# Backwards-compatible alias for the old dependency name.
get_current_user = get_request_context

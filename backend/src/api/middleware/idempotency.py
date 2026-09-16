"""
Idempotency Key Middleware

Extracts and validates X-Idempotency-Key header for duplicate prevention.
"""

from typing import Optional
from fastapi import Header, HTTPException, status
import uuid


# Header name constant
IDEMPOTENCY_HEADER = "X-Idempotency-Key"


class IdempotencyKeyHeader:
    """
    Dependency for extracting and validating idempotency keys.

    Usage:
        @router.post("/resource")
        async def create_resource(
            idempotency_key: str = Depends(IdempotencyKeyHeader(required=True))
        ):
            ...
    """

    def __init__(self, required: bool = False):
        """
        Initialize idempotency key dependency.

        Args:
            required: If True, raises 400 if header is missing
        """
        self.required = required

    def __call__(
        self,
        x_idempotency_key: Optional[str] = Header(
            None,
            alias="X-Idempotency-Key",
            description="Unique key for idempotent requests"
        )
    ) -> Optional[str]:
        """Extract and validate idempotency key."""
        if x_idempotency_key is None:
            if self.required:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Missing required header: {IDEMPOTENCY_HEADER}"
                )
            return None

        # Validate format (should be a valid UUID or similar unique string)
        if len(x_idempotency_key) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid {IDEMPOTENCY_HEADER}: too short (min 8 characters)"
            )

        if len(x_idempotency_key) > 255:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid {IDEMPOTENCY_HEADER}: too long (max 255 characters)"
            )

        return x_idempotency_key


def get_idempotency_key(
    x_idempotency_key: Optional[str] = Header(
        None,
        alias="X-Idempotency-Key",
        description="Unique key for idempotent requests (optional)"
    )
) -> Optional[str]:
    """
    Simple dependency to extract optional idempotency key.

    For routes where idempotency is optional.
    """
    if x_idempotency_key and len(x_idempotency_key) > 255:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency key too long (max 255 characters)"
        )
    return x_idempotency_key


def require_idempotency_key(
    x_idempotency_key: str = Header(
        ...,
        alias="X-Idempotency-Key",
        description="Unique key for idempotent requests (required)"
    )
) -> str:
    """
    Dependency that requires idempotency key.

    For routes where idempotency is mandatory (mutations).
    """
    if len(x_idempotency_key) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency key too short (min 8 characters)"
        )

    if len(x_idempotency_key) > 255:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency key too long (max 255 characters)"
        )

    return x_idempotency_key

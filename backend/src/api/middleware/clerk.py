"""
Clerk authentication.

Verifies a Clerk-issued session JWT (RS256) against Clerk's JWKS, then resolves
the local tenancy context (Organization + User), just-in-time provisioning them
on first sight. Replaces the half-written Supabase auth path.

Design notes:
- The JWKS is fetched from ``CLERK_JWKS_URL`` and cached. For tests, a JWKS dict
  can be injected so verification runs end-to-end without network or real keys.
- ``RequestContext`` is what routes depend on; it carries both the Clerk ids and
  the resolved local ``user_id``/``org_id`` used to scope queries.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

import jwt
from jwt import PyJWKClient
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.session import get_db


@dataclass
class ClerkConfig:
    jwks_url: str = ""
    issuer: str = ""
    audience: str = ""
    # Skip signature verification for local dev ONLY (never in production).
    dev_unsafe_accept_unsigned: bool = False

    @classmethod
    def from_env(cls) -> "ClerkConfig":
        return cls(
            jwks_url=os.getenv("CLERK_JWKS_URL", ""),
            issuer=os.getenv("CLERK_ISSUER", ""),
            audience=os.getenv("CLERK_AUDIENCE", ""),
            dev_unsafe_accept_unsigned=os.getenv("CLERK_DEV_UNSAFE", "").lower() == "true",
        )


@dataclass
class RequestContext:
    """Resolved tenancy context for the authenticated request."""
    user_id: str          # local User.id
    org_id: str           # local Organization.id
    clerk_user_id: str
    clerk_org_id: Optional[str]
    email: Optional[str]
    role: str


class ClerkVerifier:
    """Verifies Clerk session JWTs and returns their claims."""

    def __init__(self, config: ClerkConfig, jwks: Optional[dict] = None):
        self.config = config
        self._jwks = jwks              # injectable for tests
        self._jwk_client: Optional[PyJWKClient] = None

    def _signing_key(self, token: str):
        if self._jwks is not None:
            # Test / injected path: build a key from the matching JWK.
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            for key in self._jwks.get("keys", []):
                if key.get("kid") == kid:
                    return jwt.algorithms.RSAAlgorithm.from_jwk(key)
            raise HTTPException(status_code=401, detail="Unknown signing key")
        if not self.config.jwks_url:
            raise HTTPException(status_code=500, detail="CLERK_JWKS_URL not configured")
        if self._jwk_client is None:
            self._jwk_client = PyJWKClient(self.config.jwks_url)
        return self._jwk_client.get_signing_key_from_jwt(token).key

    def verify(self, token: str) -> dict:
        options = {"verify_aud": bool(self.config.audience)}
        try:
            if self.config.dev_unsafe_accept_unsigned:
                claims = jwt.decode(token, options={"verify_signature": False})
            else:
                claims = jwt.decode(
                    token,
                    self._signing_key(token),
                    algorithms=["RS256"],
                    audience=self.config.audience or None,
                    issuer=self.config.issuer or None,
                    options=options,
                )
        except HTTPException:
            raise
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError as exc:
            raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")

        # Clerk tokens carry an 'exp'; guard clock issues explicitly too.
        if "exp" in claims and claims["exp"] < int(time.time()):
            raise HTTPException(status_code=401, detail="Token expired")
        return claims


# Module-level default verifier, lazily built from env. Overridable in tests
# via ``set_verifier``.
_verifier: Optional[ClerkVerifier] = None


def get_verifier() -> ClerkVerifier:
    global _verifier
    if _verifier is None:
        _verifier = ClerkVerifier(ClerkConfig.from_env())
    return _verifier


def set_verifier(verifier: Optional[ClerkVerifier]) -> None:
    """Inject a verifier (tests) or reset to env-based default with None."""
    global _verifier
    _verifier = verifier


def _extract_bearer(request: Request) -> str:
    authorization = request.headers.get("Authorization", "")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return parts[1]


async def get_request_context(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> RequestContext:
    """
    FastAPI dependency: authenticate the request and resolve tenancy context,
    JIT-provisioning the Organization + User on first sight.
    """
    from src.tenancy.service import resolve_context  # local import avoids cycle

    token = _extract_bearer(request)
    claims = get_verifier().verify(token)
    return await resolve_context(db, claims)


async def get_current_org_id(ctx: RequestContext = Depends(get_request_context)) -> str:
    return ctx.org_id

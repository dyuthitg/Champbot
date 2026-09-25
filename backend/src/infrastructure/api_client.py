"""
LinkedIn transport factory + composite router.

``get_transport(account)`` returns a :class:`CompositeTransport` that tries the
mobile-API transport first and transparently falls back to Playwright when the
mobile transport signals it can't handle the action (``TransportUnavailable``)
or the account hits a verification wall (``TransportChallenge``). This is the
single seam the interaction/inbox/content code calls; neither caller nor the
transports know about each other.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from src.infrastructure.transports.base import (
    ACTION_METHODS,
    LinkedInTransport,
    TransportChallenge,
    TransportResult,
    TransportUnavailable,
)
from src.infrastructure.transports.mobile import MobileAPITransport
from src.infrastructure.transports.playwright import PlaywrightTransport

_FALLBACK_ON = (TransportUnavailable, TransportChallenge)

# Lazily-constructed, process-wide default executor: real chromium, launched
# on first actual use (constructing it here does nothing eager). Explicit
# `playwright_executor=` on get_transport() always overrides this -- tests do
# this to inject a fake. Before this existed, every caller left the fallback
# executor as None, so Playwright never actually worked as a backup for
# anyone -- see playwright_executor.py's module docstring for why.
_default_browser_executor = None


def _get_default_browser_executor():
    global _default_browser_executor
    if _default_browser_executor is None:
        from src.infrastructure.transports.playwright_executor import BrowserExecutor

        _default_browser_executor = BrowserExecutor()
    return _default_browser_executor


class CompositeTransport:
    """Routes an action to ``primary`` first, falling back to ``fallback``."""

    name = "composite"

    def __init__(
        self,
        primary: LinkedInTransport,
        fallback: Optional[LinkedInTransport] = None,
        fallback_on: tuple = _FALLBACK_ON,
    ):
        self.primary = primary
        self.fallback = fallback
        self.fallback_on = fallback_on

    async def _dispatch(self, action: str, *args, **kwargs) -> TransportResult:
        try:
            return await getattr(self.primary, action)(*args, **kwargs)
        except self.fallback_on as exc:
            if self.fallback is None:
                return TransportResult(
                    success=False, action=action, via=self.primary.name, error=str(exc)
                )
            try:
                result = await getattr(self.fallback, action)(*args, **kwargs)
                if result.detail is None:
                    result.detail = {}
                result.detail["fell_back_from"] = self.primary.name
                result.detail["fallback_reason"] = str(exc)
                return result
            except self.fallback_on as exc2:
                # Report BOTH failures. Reporting only the fallback's is how a
                # real diagnosis gets lost: while the Playwright executor is
                # unbound, its error is always the same uninformative sentence,
                # and it would mask the Voyager response that actually explains
                # what went wrong — exactly what you need when validating the
                # mobile endpoints against a live account.
                return TransportResult(
                    success=False,
                    action=action,
                    via=self.fallback.name,
                    error=(
                        f"{self.primary.name}: {exc} || {self.fallback.name}: {exc2}"
                    ),
                    detail={
                        "primary_via": self.primary.name,
                        "primary_error": str(exc),
                        "fallback_via": self.fallback.name,
                        "fallback_error": str(exc2),
                    },
                )

    async def like(self, account: Any, activity_urn: str) -> TransportResult:
        return await self._dispatch("like", account, activity_urn)

    async def comment(self, account: Any, activity_urn: str, text: str) -> TransportResult:
        return await self._dispatch("comment", account, activity_urn, text)

    async def follow(self, account: Any, member_urn: str) -> TransportResult:
        return await self._dispatch("follow", account, member_urn)

    async def connect(self, account: Any, member_urn: str, note: Optional[str] = None) -> TransportResult:
        return await self._dispatch("connect", account, member_urn, note)

    async def send_message(self, account: Any, member_urn: str, text: str) -> TransportResult:
        return await self._dispatch("send_message", account, member_urn, text)

    async def create_post(self, account: Any, body: str, media: Any = None) -> TransportResult:
        return await self._dispatch("create_post", account, body, media)

    async def fetch_activity(self, account: Any, member_urn: str) -> TransportResult:
        return await self._dispatch("fetch_activity", account, member_urn)

    async def fetch_inbox(self, account: Any, since: Any = None) -> TransportResult:
        return await self._dispatch("fetch_inbox", account, since)

    async def fetch_profile(self, account: Any, public_id: str) -> TransportResult:
        return await self._dispatch("fetch_profile", account, public_id)

    async def fetch_connections(self, account: Any, since: Any = None) -> TransportResult:
        return await self._dispatch("fetch_connections", account, since)

    async def whoami(self, account: Any) -> TransportResult:
        return await self._dispatch("whoami", account)


def get_transport(
    account: Any,
    *,
    playwright_executor: Any = None,
    mobile_session_factory: Any = None,
) -> LinkedInTransport:
    """
    Build the transport for an account.

    Honors ``MOBILE_TRANSPORT_ENABLED`` (default true). When disabled, returns a
    Playwright-only transport so operators can pin to the browser path.

    ``playwright_executor`` defaults to a shared, real ``BrowserExecutor`` (a
    real chromium instance, launched lazily on first use) rather than
    ``None`` -- pass an explicit executor (fake or real) to override, which
    is what tests do. Only ``like``/``comment`` actually work through it
    today; see ``playwright_executor.py``'s module docstring for the honest
    reason ``follow``/``connect``/the ``fetch_*`` reads don't.
    """
    mobile_enabled = os.getenv("MOBILE_TRANSPORT_ENABLED", "true").lower() != "false"
    if playwright_executor is None:
        playwright_executor = _get_default_browser_executor()
    playwright = PlaywrightTransport(executor=playwright_executor)

    if not mobile_enabled:
        return playwright

    mobile = MobileAPITransport(session_factory=mobile_session_factory)
    return CompositeTransport(primary=mobile, fallback=playwright)


# Ensure the composite implements the full action surface (guards drift).
assert all(hasattr(CompositeTransport, m) for m in ACTION_METHODS)

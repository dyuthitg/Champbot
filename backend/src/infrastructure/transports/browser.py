"""
Browser transport (fallback).

Puts real-browser automation behind the transport interface so the composite
router can fall back to it whenever the mobile API can't handle an action or
the account hits a challenge.

It delegates to an injected ``executor`` object exposing async action methods
(``like``, ``comment``, ``fetch_inbox``, ...). In the running system that's
:class:`~src.infrastructure.transports.harness_executor.HarnessExecutor`
(browser-harness driving a per-account Chrome over CDP); in tests a fake
executor is injected. An executor that lacks a method, or no executor at all,
raises ``TransportUnavailable`` so the router surfaces a clear failure rather
than silently no-op-ing.

This used to be ``PlaywrightTransport`` wrapping a Playwright executor. That
version is preserved on the ``playwright-fallback`` git branch.
"""

from __future__ import annotations

from typing import Any, Optional

from src.infrastructure.transports.base import (
    TransportResult,
    TransportUnavailable,
)


class BrowserTransport:
    name = "browser"

    def __init__(self, executor: Any = None):
        self._executor = executor

    async def _delegate(self, action: str, *args, **kwargs) -> TransportResult:
        if self._executor is None:
            raise TransportUnavailable(f"no browser executor bound for {action}")
        method = getattr(self._executor, action, None)
        if method is None:
            raise TransportUnavailable(f"browser executor lacks {action}")
        result = await method(*args, **kwargs)
        # Executors may return a TransportResult or a truthy value.
        if isinstance(result, TransportResult):
            result.via = self.name
            return result
        return TransportResult(success=bool(result), action=action, via=self.name)

    async def like(self, account: Any, activity_urn: str) -> TransportResult:
        return await self._delegate("like", account, activity_urn)

    async def comment(self, account: Any, activity_urn: str, text: str) -> TransportResult:
        return await self._delegate("comment", account, activity_urn, text)

    async def follow(self, account: Any, member_urn: str) -> TransportResult:
        return await self._delegate("follow", account, member_urn)

    async def connect(self, account: Any, member_urn: str, note: Optional[str] = None) -> TransportResult:
        return await self._delegate("connect", account, member_urn, note)

    async def send_message(self, account: Any, member_urn: str, text: str) -> TransportResult:
        return await self._delegate("send_message", account, member_urn, text)

    async def create_post(self, account: Any, body: str, media: Any = None) -> TransportResult:
        return await self._delegate("create_post", account, body, media)

    async def fetch_activity(self, account: Any, member_urn: str) -> TransportResult:
        return await self._delegate("fetch_activity", account, member_urn)

    async def fetch_inbox(self, account: Any, since: Any = None) -> TransportResult:
        return await self._delegate("fetch_inbox", account, since)

    async def fetch_profile(self, account: Any, public_id: str) -> TransportResult:
        return await self._delegate("fetch_profile", account, public_id)

    async def fetch_connections(self, account: Any, since: Any = None) -> TransportResult:
        return await self._delegate("fetch_connections", account, since)

    async def whoami(self, account: Any) -> TransportResult:
        return await self._delegate("whoami", account)

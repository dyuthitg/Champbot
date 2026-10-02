"""
Check a proxy before an account is allowed to use it.

LinkedIn ties a session to where it is used from. A "rotating" residential
proxy hands out a new exit IP -- often in a different country -- on every
request, and LinkedIn answers that by signing the session out. So a proxy is
only accepted if it (a) works and (b) keeps the same exit IP across requests.

For DataImpulse that means a sticky port (10000 and up, one per account)
rather than the rotating gateway port 823, ideally with a country pinned in
the login, e.g. ``http://LOGIN__cr.in:PASS@gw.dataimpulse.com:10000``.
"""

from __future__ import annotations

import urllib.parse
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

import httpx

_IP_ECHO_URL = "https://ipinfo.io/json"
_TIMEOUT_SECONDS = 20.0
_ALLOWED_SCHEMES = ("http", "https", "socks5")

# (proxy_url) -> {"ip": ..., "country": ..., "city": ...}
Fetcher = Callable[[str], Awaitable[dict]]


class ProxyCheckError(ValueError):
    """The proxy is unusable for a LinkedIn account; message is user-facing."""


async def _default_fetch(proxy_url: str) -> dict:
    async with httpx.AsyncClient(proxy=proxy_url, timeout=_TIMEOUT_SECONDS) as client:
        response = await client.get(_IP_ECHO_URL)
        response.raise_for_status()
        return response.json()


def normalize(proxy_url: Optional[str]) -> Optional[str]:
    """Trim and validate the shape of a proxy URL. Empty means 'no proxy'."""
    url = (proxy_url or "").strip()
    if not url:
        return None
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.hostname or not parsed.port:
        raise ProxyCheckError(
            "Proxy must look like http://login:password@host:port"
        )
    return url


def redact(proxy_url: Optional[str]) -> Optional[str]:
    """``host:port`` only -- never the login or password."""
    if not proxy_url:
        return None
    parsed = urllib.parse.urlsplit(proxy_url)
    return f"{parsed.hostname}:{parsed.port}"


async def check(proxy_url: str, *, fetch: Optional[Fetcher] = None) -> dict:
    """
    Make two requests through the proxy and return what to store on the account.

    Raises :class:`ProxyCheckError` if the proxy fails or its exit IP changes.
    """
    fetch = fetch or _default_fetch
    seen = []
    for _ in range(2):
        try:
            seen.append(await fetch(proxy_url))
        except Exception as exc:
            raise ProxyCheckError(
                f"Couldn't connect through this proxy ({type(exc).__name__}). "
                "Check the host, port, login and password."
            ) from exc

    first, second = seen
    if not first.get("ip") or first.get("ip") != second.get("ip"):
        raise ProxyCheckError(
            "This proxy changes its address on every request "
            f"({first.get('country')} then {second.get('country')}). LinkedIn "
            "signs the account out when that happens. Use a sticky address -- "
            "for DataImpulse, a port from 10000 up instead of 823."
        )

    return {
        "url": proxy_url,
        "ip": first.get("ip"),
        "country": first.get("country"),
        "city": first.get("city"),
        # The account's active hours follow this unless set explicitly.
        "timezone": first.get("timezone"),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }

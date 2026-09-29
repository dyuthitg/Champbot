"""
Per-account Chrome processes for the browser-harness fallback.

browser-harness never launches a browser itself: its daemon attaches over CDP
to a Chrome that is already running (``BU_CDP_URL``). This pool is the piece
that owns those Chromes -- one per account, launched lazily on first use,
reused while warm, and shut down after an idle TTL or on app shutdown.

One Chrome per account (rather than one shared Chrome with many contexts) is
deliberate: each gets its own ``--user-data-dir`` so LinkedIn sees a stable,
separate browser profile per account, and its own ``--proxy-server`` so the
fallback leaves from the same IP as that account's mobile traffic. Sending an
account's ``li_at`` from a different IP than its normal traffic is exactly the
mismatch LinkedIn's fraud detection watches for.

Proxy credentials: Chrome's ``--proxy-server`` flag has no way to carry
``user:pass``. When ``account.proxy["url"]`` has credentials, the pool starts a
local no-auth forwarder (``pproxy``) on loopback that adds them upstream, and
points Chrome at the forwarder instead.

Every process launch goes through an injectable ``launcher`` and readiness
goes through an injectable ``probe``, so tests never spawn anything.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from src.infrastructure.transports.base import TransportUnavailable

_CHROME_CANDIDATES = (
    "chromium",
    "chromium-browser",
    "google-chrome",
    "google-chrome-stable",
    "chrome",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
)

_DEFAULT_IDLE_TTL_SECONDS = 600
_READY_TIMEOUT_SECONDS = 20.0

Launcher = Callable[[list], Awaitable[Any]]
Probe = Callable[[str], Awaitable[bool]]
# Called with a handle just before its Chrome is stopped, so whatever attached
# to it (the per-account browser-harness daemon) can be shut down too.
OnRelease = Callable[["ChromeHandle"], Awaitable[None]]


def harness_python() -> str:
    """
    Interpreter for browser-harness and pproxy.

    They live in their own virtualenv (``HARNESS_PYTHON``, set in the
    Dockerfile) because browser-harness pins ``websockets==15`` while this app
    pins ``websockets<13``; both only ever run as subprocesses, so they never
    need to share an environment with the app. Falls back to this interpreter
    for local runs where they're installed alongside everything else.
    """
    return os.getenv("HARNESS_PYTHON") or sys.executable


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def find_chrome() -> Optional[str]:
    """``CHROME_BIN`` if set, else the first Chrome/Chromium found on this box."""
    explicit = os.getenv("CHROME_BIN")
    if explicit:
        return explicit
    for candidate in _CHROME_CANDIDATES:
        found = shutil.which(candidate)
        if found:
            return found
        if os.path.isabs(candidate) and os.path.exists(candidate):
            return candidate
    return None


def proxy_plan(proxy_url: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """
    Decide how Chrome reaches the account's proxy.

    Returns ``(chrome_proxy_server, forwarder_remote)``:
    - no proxy            -> ``(None, None)``
    - proxy without creds -> ``("scheme://host:port", None)``, Chrome dials it directly
    - proxy with creds    -> ``(None, "scheme://host:port#user:pass")``, a pproxy
      forwarder is needed; the caller fills in Chrome's server once the
      forwarder's local port is known.
    """
    if not proxy_url:
        return None, None
    parsed = urllib.parse.urlsplit(proxy_url)
    scheme = parsed.scheme or "http"
    host = parsed.hostname or ""
    netloc = f"{host}:{parsed.port}" if parsed.port else host
    if not parsed.username:
        return f"{scheme}://{netloc}", None
    user = urllib.parse.unquote(parsed.username)
    password = urllib.parse.unquote(parsed.password or "")
    return None, f"{scheme}://{netloc}#{user}:{password}"


def chrome_argv(
    chrome: str,
    *,
    port: int,
    profile_dir: Path,
    proxy_server: Optional[str],
    headless: bool,
) -> list:
    argv = [
        chrome,
        f"--remote-debugging-port={port}",
        "--remote-debugging-address=127.0.0.1",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--disable-dev-shm-usage",
        "--window-size=1920,1080",
    ]
    if headless:
        argv.append("--headless=new")
    if os.getenv("CHROME_NO_SANDBOX", "").lower() in {"1", "true", "yes"}:
        # Containers running as a non-root user usually have no usable
        # namespace sandbox; the Dockerfile opts into this explicitly.
        argv.append("--no-sandbox")
    if proxy_server:
        argv.append(f"--proxy-server={proxy_server}")
    argv.append("about:blank")
    return argv


async def _default_launcher(argv: list):
    return await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )


async def _default_probe(cdp_url: str) -> bool:
    def _check() -> bool:
        try:
            with urllib.request.urlopen(f"{cdp_url}/json/version", timeout=1) as response:
                return bool(json.loads(response.read()).get("webSocketDebuggerUrl"))
        except (OSError, ValueError):
            return False

    return await asyncio.to_thread(_check)


@dataclass
class ChromeHandle:
    account_id: str
    cdp_url: str
    bu_name: str
    chrome: Any
    forwarder: Any = None
    last_used: float = field(default_factory=time.monotonic)

    def alive(self) -> bool:
        return getattr(self.chrome, "returncode", None) is None


async def _stop(proc: Any) -> None:
    if proc is None or getattr(proc, "returncode", None) is not None:
        return
    try:
        proc.terminate()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(proc.wait(), timeout=5)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()


class ChromePool:
    def __init__(
        self,
        *,
        data_dir: Optional[Path] = None,
        idle_ttl: Optional[float] = None,
        headless: Optional[bool] = None,
        launcher: Launcher = _default_launcher,
        probe: Probe = _default_probe,
        chrome_bin: Optional[str] = None,
        clock: Callable[[], float] = time.monotonic,
        on_release: Optional[OnRelease] = None,
    ):
        self._data_dir = Path(data_dir or os.getenv("CHROME_DATA_DIR", "data/chrome"))
        self._idle_ttl = float(
            idle_ttl if idle_ttl is not None
            else os.getenv("CHROME_IDLE_TTL_SECONDS", _DEFAULT_IDLE_TTL_SECONDS)
        )
        self._headless = (
            headless if headless is not None
            else os.getenv("CHROME_HEADLESS", "true").lower() != "false"
        )
        self._launcher = launcher
        self._probe = probe
        self._chrome_bin = chrome_bin
        self._clock = clock
        self.on_release = on_release
        self._handles: dict[str, ChromeHandle] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def get(self, account: Any) -> ChromeHandle:
        """The warm Chrome for this account, launching one if needed."""
        account_id = str(getattr(account, "id", "") or "")
        if not account_id:
            raise TransportUnavailable("browser fallback needs an account id")
        await self.reap_idle()
        lock = self._locks.setdefault(account_id, asyncio.Lock())
        async with lock:
            handle = self._handles.get(account_id)
            if handle is not None and handle.alive():
                handle.last_used = self._clock()
                return handle
            if handle is not None:
                # Chrome died underneath us; clean up and relaunch.
                self._handles.pop(account_id, None)
                await self._release(handle)
            handle = await self._launch(account_id, getattr(account, "proxy", None))
            self._handles[account_id] = handle
            return handle

    async def _launch(self, account_id: str, proxy: Any) -> ChromeHandle:
        chrome = self._chrome_bin or find_chrome()
        if not chrome:
            raise TransportUnavailable(
                "no Chrome/Chromium found for the browser fallback (set CHROME_BIN)"
            )

        proxy_url = proxy.get("url") if isinstance(proxy, dict) else None
        proxy_server, forwarder_remote = proxy_plan(proxy_url)
        forwarder = None
        if forwarder_remote:
            local_port = _free_port()
            forwarder = await self._launcher(
                [harness_python(), "-m", "pproxy", "-l", f"http://127.0.0.1:{local_port}",
                 "-r", forwarder_remote, "-q"]
            )
            proxy_server = f"http://127.0.0.1:{local_port}"

        port = _free_port()
        profile_dir = (self._data_dir / _safe_dirname(account_id)).resolve()
        profile_dir.mkdir(parents=True, exist_ok=True)
        argv = chrome_argv(
            chrome,
            port=port,
            profile_dir=profile_dir,
            proxy_server=proxy_server,
            headless=self._headless,
        )
        try:
            proc = await self._launcher(argv)
        except (OSError, FileNotFoundError) as exc:
            await _stop(forwarder)
            raise TransportUnavailable(f"could not launch Chrome: {exc}") from exc

        cdp_url = f"http://127.0.0.1:{port}"
        deadline = self._clock() + _READY_TIMEOUT_SECONDS
        while not await self._probe(cdp_url):
            if getattr(proc, "returncode", None) is not None or self._clock() > deadline:
                await _stop(proc)
                await _stop(forwarder)
                raise TransportUnavailable("Chrome did not expose its DevTools endpoint in time")
            await asyncio.sleep(0.25)

        return ChromeHandle(
            account_id=account_id,
            cdp_url=cdp_url,
            bu_name=f"acct-{_safe_dirname(account_id)}",
            chrome=proc,
            forwarder=forwarder,
            last_used=self._clock(),
        )

    def touch(self, handle: ChromeHandle) -> None:
        handle.last_used = self._clock()

    async def reap_idle(self) -> list[str]:
        """Stop Chromes unused for longer than the idle TTL. Returns reaped ids."""
        now = self._clock()
        stale = [
            account_id for account_id, handle in self._handles.items()
            if now - handle.last_used > self._idle_ttl
            and not self._locks.get(account_id, asyncio.Lock()).locked()
        ]
        for account_id in stale:
            await self._close_one(account_id)
        return stale

    async def _close_one(self, account_id: str) -> None:
        handle = self._handles.pop(account_id, None)
        if handle is not None:
            await self._release(handle)

    async def _release(self, handle: ChromeHandle) -> None:
        if self.on_release is not None:
            try:
                await self.on_release(handle)
            except Exception:
                pass  # best effort: never let cleanup block stopping Chrome
        await _stop(handle.chrome)
        await _stop(handle.forwarder)

    async def close(self) -> None:
        for account_id in list(self._handles):
            await self._close_one(account_id)

    def handles(self) -> list[ChromeHandle]:
        return list(self._handles.values())


def _safe_dirname(account_id: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in account_id)

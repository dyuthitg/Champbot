"""
browser-harness executor for the :class:`BrowserTransport` fallback.

How it runs
-----------
Each action is a short, fixed Python script run through the ``browser-harness``
CLI as a subprocess (``python -m browser_harness.run``, script on stdin), with
``BU_CDP_URL`` pointing at that account's Chrome from :class:`ChromePool` and
``BU_NAME`` naming a per-account harness daemon. A subprocess rather than an
in-process import, because the harness helpers are synchronous and bind
``BU_NAME`` at import time -- one Python process can't cleanly drive several
accounts through them. The script prints one ``CHAMP_RESULT {...}`` line that
is parsed back into a :class:`TransportResult`.

Pages are scripted deterministically (fixed selectors, fixed steps). No LLM
drives anything here, even though browser-harness is built for that.

Secrets never go into script text
---------------------------------
browser-harness ships opt-out telemetry that uploads the *script text* and the
tail of stdout to PostHog. So: ``BH_TELEMETRY=0`` is always set, AND cookies
and action arguments travel in environment variables (``CHAMP_COOKIES`` /
``CHAMP_ARGS``), never interpolated into the script, and the result line
never echoes them. Either guard alone would keep ``li_at`` on this box; both
are kept so a future harness change to the opt-out can't leak a session.

What works
----------
``like``, ``comment`` and ``fetch_inbox``. The Like/Comment selector lists are
the ones the old Playwright executor used (preserved on the
``playwright-fallback`` branch). ``fetch_inbox`` does NOT scrape the
conversation list DOM, because the list items carry no profile links and
opening each thread to find one would mark it read on the operator's account.
Instead it loads ``/messaging/`` and reads the JSON responses LinkedIn's own
page fetched (captured via CDP ``Network`` events, which the harness daemon
already buffers), then normalizes them into the shape
``outreach.sync._inbound_participants`` parses.

Verification status: none of the selectors or the messenger-payload shapes
here have been confirmed against a live, logged-in session yet. Treat them as
current-as-written until ``validate_account.py`` passes against a real account.
Everything else (``follow``, ``connect``, ``whoami``, ...) is deliberately
absent, so :class:`BrowserTransport` reports "browser executor lacks X".
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from src.infrastructure.transports.base import (
    TransportChallenge,
    TransportResult,
    TransportUnavailable,
)
from src.infrastructure.transports.chrome_pool import ChromePool, harness_python
from src.infrastructure.transports.mobile import parse_auth_blob

RESULT_PREFIX = "CHAMP_RESULT "
_DEFAULT_TIMEOUT_SECONDS = 90.0

# (returncode, stdout, stderr)
Runner = Callable[[str, dict, float], Awaitable[tuple]]

_LIKE_BUTTON_SELECTORS = [
    'button[aria-label*="Like"]',
    'button[data-control-name="like"]',
    "button.react-button__trigger",
    "span.reactions-react-button",
]

_COMMENT_BUTTON_SELECTORS = [
    'button[aria-label*="Comment"]',
    'button[data-control-name="comment"]',
    "button.comment-button",
    "span.feed-shared-social-action-bar__comment-action-button",
]

_COMMENT_INPUT_SELECTORS = [
    'div[contenteditable="true"][role="textbox"]',
    "div.ql-editor",
    "div.mentions-texteditor__content",
    "div.comment-box__texteditor",
]

_POST_BUTTON_SELECTORS = [
    'button[aria-label="Post comment"]',
    "button.comments-comment-box__submit-button",
    'button.comment-button[type="submit"]',
]

# Response URLs worth reading on /messaging/. The GraphQL one is what the
# current web client uses; the REST one is the legacy shape mobile.py tries.
_INBOX_URL_MARKERS = [
    "messengerConversations",
    "voyagerMessagingGraphQL",
    "/voyager/api/messaging/conversations",
]

# ----------------------------------------------------------------------
# Scripts. Executed by browser-harness with its helpers (cdp, js, goto_url,
# new_tab, ensure_real_tab, wait_for_load, wait_for_element, click_at_xy,
# type_text, drain_events, ...) already in globals. No secrets in here.
# ----------------------------------------------------------------------

_PREAMBLE = r'''
import json as _json, os as _os, random as _random, time as _time

ARGS = _json.loads(_os.environ["CHAMP_ARGS"])

def _emit(**payload):
    print("CHAMP_RESULT " + _json.dumps(payload), flush=True)

# Network responses matching ARGS["url_markers"], collected while we wait.
# The harness daemon buffers only the last 500 CDP events, and a LinkedIn
# page fires hundreds of image/tracking requests -- so events are drained
# continuously during every wait instead of once at the end, or the one
# response we need can be evicted before we look.
CAPTURED = {}

def _tick():
    markers = ARGS.get("url_markers")
    if not markers:
        return
    for event in drain_events():
        if event.get("method") != "Network.responseReceived":
            continue
        params = event.get("params") or {}
        url = (params.get("response") or {}).get("url") or ""
        rid = params.get("requestId")
        if rid and any(m in url for m in markers):
            CAPTURED[rid] = {"url": url, "session_id": event.get("session_id")}

def _sleep(seconds):
    end = _time.time() + seconds
    while True:
        _tick()
        left = end - _time.time()
        if left <= 0:
            return
        _time.sleep(min(0.3, left))

def _pause(lo, hi):
    _sleep(_random.uniform(lo, hi))

def _wait_js(expression, timeout):
    end = _time.time() + timeout
    while _time.time() < end:
        _tick()
        if js(expression):
            return True
        _time.sleep(0.3)
    return False

def _open(url, expect):
    cdp("Network.setCookies", cookies=_json.loads(_os.environ["CHAMP_COOKIES"]))
    if ensure_real_tab() is None:
        new_tab("about:blank")
    drain_events()  # start clean: nothing from a previous page counts
    # Not goto_url(): that uses the harness's default 5s IPC timeout, and
    # Page.navigate only answers once the navigation commits -- LinkedIn's
    # redirect chain regularly takes longer than that.
    cdp("Page.navigate", url=url, _response_timeout=45)
    _wait_js("document.readyState === 'complete'", 30)
    _pause(2.0, 4.0)
    here = (js("location.href") or "").split("?")[0]
    if here.startswith("chrome-error:"):
        # Chrome's own network-error page, not a LinkedIn wall. A dead li_at
        # typically shows up here as ERR_TOO_MANY_REDIRECTS.
        code = js("(document.querySelector('.error-code') || {}).innerText || ''") or "unknown error"
        _emit(ok=False, error="navigation to " + url.split("?")[0] + " failed: " + code.strip())
        raise SystemExit(0)
    # A dead or challenged session doesn't always land on /login: LinkedIn
    # also bounces to the guest homepage, /authwall or /checkpoint. So check
    # we arrived where we meant to, not for a list of known bad places.
    if expect not in here:
        _emit(ok=False, challenge=True, error="LinkedIn redirected to " + here)
        raise SystemExit(0)

_FIND_JS = """(() => {
  for (const s of %s) {
    const e = document.querySelector(s);
    if (!e) continue;
    e.scrollIntoView({block: 'center'});
    const b = e.getBoundingClientRect();
    if (!b.width || !b.height) continue;
    return {sel: s, x: b.x + b.width / 2, y: b.y + b.height / 2,
            pressed: e.getAttribute('aria-pressed')};
  }
  return null;
})()"""

def _find(selectors, timeout=8.0):
    deadline = _time.time() + timeout
    while _time.time() < deadline:
        hit = js(_FIND_JS % _json.dumps(selectors))
        if hit:
            return hit
        _time.sleep(0.4)
    return None

def _click(hit):
    click_at_xy(hit["x"], hit["y"])
'''

_LIKE_SCRIPT = _PREAMBLE + r'''
_open(ARGS["url"], "/feed/update/")
hit = _find(ARGS["like_selectors"])
if not hit:
    _emit(ok=False, error="like: no matching like button found on the page")
elif hit.get("pressed") == "true":
    _emit(ok=True, detail={"already_liked": True})
else:
    _click(hit)
    _pause(1.0, 2.0)
    after = _find([hit["sel"]], timeout=3.0)
    if after and after.get("pressed") == "true":
        _emit(ok=True, detail={"selector": hit["sel"]})
    else:
        _emit(ok=False, error="like: clicked, but the button never showed as pressed")
'''

_COMMENT_SCRIPT = _PREAMBLE + r'''
_open(ARGS["url"], "/feed/update/")
button = _find(ARGS["comment_button_selectors"])
if not button:
    _emit(ok=False, error="comment: no comment button found on the page")
    raise SystemExit(0)
_click(button)
_pause(1.0, 2.0)
box = _find(ARGS["comment_input_selectors"])
if not box:
    _emit(ok=False, error="comment: no comment input found on the page")
    raise SystemExit(0)
_click(box)
_pause(0.4, 0.9)
type_text(ARGS["text"])
_pause(0.8, 1.6)
post = _find(ARGS["post_button_selectors"], timeout=5.0)
if not post:
    _emit(ok=False, error="comment: no post/submit button found on the page")
    raise SystemExit(0)
_click(post)
_pause(2.0, 3.0)
needle = ARGS["text"].strip()[:60]
landed = js("document.body.innerText.includes(%s)" % _json.dumps(needle))
if landed:
    _emit(ok=True)
else:
    _emit(ok=False, error="comment: posted, but the text never appeared on the page")
'''

_INBOX_SCRIPT = _PREAMBLE + r'''
_open(ARGS["url"], ARGS["expect"])
_wait_js("!!document.querySelector(%s)" % _json.dumps(ARGS["ready_selector"]), 15)
_pause(2.0, 3.5)

_ME_JS = """(async () => {
  const m = document.cookie.match(/JSESSIONID="?([^";]+)/);
  try {
    const r = await fetch('/voyager/api/me', {headers: {'csrf-token': m ? m[1] : ''}});
    const j = await r.json();
    return (j.miniProfile && j.miniProfile.entityUrn) || j.entityUrn || null;
  } catch (e) { return null; }
})()"""
try:
    me = js(_ME_JS) if ARGS.get("resolve_me") else None
except Exception:
    me = None  # normalize_inbox can infer the viewer without it
_tick()

bodies, budget = [], 4_000_000
for rid, info in CAPTURED.items():
    try:
        body = cdp("Network.getResponseBody", session_id=info["session_id"], requestId=rid)
    except Exception:
        continue  # evicted from Chrome's buffer or still streaming
    text = body.get("body") or ""
    if body.get("base64Encoded") or not text or len(text) > budget:
        continue
    budget -= len(text)
    bodies.append({"url": info["url"].split("?")[0], "body": text})

_emit(ok=True, detail={"me": me, "bodies": bodies, "matched": len(CAPTURED)})
'''


# ----------------------------------------------------------------------
# Inbox payload normalization (pure; runs in the backend, not the script).
# ----------------------------------------------------------------------


def _iter_dicts(node: Any):
    stack = [node]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            yield item
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)


def _ident(urn: Any) -> str:
    text = str(urn or "").strip().lower()
    return text.rsplit(":", 1)[-1].strip("()") if ":" in text else text


def _participant_urn(participant: Any) -> Optional[str]:
    if not isinstance(participant, dict):
        return None
    return participant.get("hostIdentityUrn") or participant.get("entityUrn")


def normalize_inbox(bodies: list, me: Optional[str] = None) -> list:
    """
    Turn captured messaging responses into ``sync._inbound_participants``'s shape.

    Two payload families are understood:
    - legacy REST (``/voyager/api/messaging/conversations``): ``elements`` are
      already conversation objects with ``events``; passed through unchanged.
    - messenger GraphQL: any dict carrying ``conversationParticipants`` is a
      conversation. Each distinct non-self message sender becomes one event,
      ``{"from": {"entityUrn": urn}}``; ``unreadCount`` is carried over, and
      so are non-self ``participants`` for the unread fallback in sync.py.

    ``me`` (the viewer's own URN) is what separates self from inbound; without
    it, a sender who appears in every conversation is assumed to be the viewer.
    """
    legacy, graph = [], []
    for item in bodies or []:
        try:
            payload = json.loads(item.get("body") or "")
        except (TypeError, ValueError):
            continue
        if "/voyager/api/messaging/conversations" in (item.get("url") or ""):
            legacy.extend(e for e in (payload.get("elements") or []) if isinstance(e, dict))
            continue
        graph.extend(d for d in _iter_dicts(payload) if "conversationParticipants" in d)

    self_id = _ident(me) if me else ""
    if not self_id and len(graph) > 1:
        common = None
        for conv in graph:
            ids = {_ident(_participant_urn(p)) for p in conv.get("conversationParticipants") or []}
            common = ids if common is None else common & ids
        if common and len(common) == 1:
            self_id = next(iter(common))

    conversations, seen = list(legacy), set()
    for conv in graph:
        key = conv.get("entityUrn") or conv.get("backendUrn") or id(conv)
        if key in seen:
            continue
        seen.add(key)

        others = []
        for p in conv.get("conversationParticipants") or []:
            urn = _participant_urn(p)
            if urn and _ident(urn) != self_id:
                others.append({"entityUrn": urn})

        senders = []
        for d in _iter_dicts(conv.get("messages") or {}):
            urn = _participant_urn(d.get("sender")) if isinstance(d.get("sender"), dict) else None
            if urn and _ident(urn) != self_id and urn not in senders:
                senders.append(urn)

        conversations.append({
            "entityUrn": conv.get("entityUrn"),
            "unreadCount": conv.get("unreadCount") or 0,
            "participants": others,
            "events": [{"from": {"entityUrn": urn}} for urn in senders],
        })
    return conversations


# ----------------------------------------------------------------------
# Executor
# ----------------------------------------------------------------------


def _activity_url(activity_urn: str) -> str:
    urn = activity_urn if str(activity_urn).startswith("urn:") else f"urn:li:activity:{activity_urn}"
    return f"https://www.linkedin.com/feed/update/{urn}/"


def _cookies(account: Any) -> list:
    creds = parse_auth_blob(getattr(account, "auth_blob", None))
    if not creds.get("li_at"):
        raise TransportUnavailable("account has no li_at session cookie")
    cookies = [{
        "name": "li_at", "value": creds["li_at"], "domain": ".linkedin.com",
        "path": "/", "secure": True, "httpOnly": True,
    }]
    if creds.get("jsessionid"):
        cookies.append({
            "name": "JSESSIONID", "value": f'"{creds["jsessionid"]}"',
            "domain": ".linkedin.com", "path": "/", "secure": True,
        })
    return cookies


async def _default_runner(script: str, env: dict, timeout: float) -> tuple:
    extra = ["--reload"] if env.get("CHAMP_STOP_DAEMON") else []
    proc = await asyncio.create_subprocess_exec(
        harness_python(), "-m", "browser_harness.run", *extra,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(script.encode("utf-8")), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise TransportUnavailable(f"browser-harness timed out after {int(timeout)}s")
    return proc.returncode, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


def parse_result(stdout: str) -> Optional[dict]:
    """The last ``CHAMP_RESULT`` line on stdout, decoded; ``None`` if absent."""
    for line in reversed((stdout or "").splitlines()):
        if line.startswith(RESULT_PREFIX):
            try:
                return json.loads(line[len(RESULT_PREFIX):])
            except ValueError:
                return None
    return None


class HarnessExecutor:
    """Injected into :class:`BrowserTransport` as its ``executor``."""

    def __init__(
        self,
        pool: Optional[ChromePool] = None,
        *,
        runner: Runner = _default_runner,
        timeout: float = _DEFAULT_TIMEOUT_SECONDS,
        harness_home: Optional[Path] = None,
    ):
        self._pool = pool or ChromePool()
        if self._pool.on_release is None:
            self._pool.on_release = self._stop_daemon
        self._runner = runner
        self._timeout = timeout
        self._harness_home = Path(harness_home or os.getenv("BH_HOME", "data/harness")).resolve()

    async def close(self) -> None:
        await self._pool.close()

    async def _stop_daemon(self, handle) -> None:
        """
        Stop the account's harness daemon when its Chrome goes away.

        The daemon is spawned by the first script run and is not a child we
        hold a handle to, so it would otherwise outlive its Chrome (found in
        the local smoke run). ``--reload`` is the harness's own clean stop.
        """
        env = self._env(handle, [], {})
        await self._runner("", {**env, "CHAMP_STOP_DAEMON": "1"}, 15.0)

    def _env(self, handle, cookies: list, args: dict) -> dict:
        env = {
            k: v for k, v in os.environ.items()
            # Never let a stray cloud key make the harness spin up a paid
            # remote browser instead of the Chrome we just launched.
            if not k.startswith(("BU_", "BROWSER_USE_", "CHAMP_"))
        }
        env.update({
            "BU_NAME": handle.bu_name,
            "BU_CDP_URL": handle.cdp_url,
            "BH_HOME": str(self._harness_home),
            "BH_TELEMETRY": "0",
            "PYTHONIOENCODING": "utf-8",
            "CHAMP_COOKIES": json.dumps(cookies),
            "CHAMP_ARGS": json.dumps(args),
        })
        return env

    async def _run(self, action: str, account: Any, script: str, args: dict) -> dict:
        cookies = _cookies(account)
        handle = await self._pool.get(account)
        env = self._env(handle, cookies, args)
        try:
            code, out, err = await self._runner(script, env, self._timeout)
        finally:
            # A long action must not look idle to the reaper right after it ends.
            self._pool.touch(handle)
        result = parse_result(out)
        if result is None:
            tail = (err or out or "").strip().splitlines()[-1:] or [f"exit {code}"]
            raise TransportUnavailable(f"browser-harness {action} produced no result: {tail[0][:300]}")
        if result.get("challenge"):
            raise TransportChallenge(result.get("error") or "LinkedIn verification wall")
        return result

    @staticmethod
    def _to_result(action: str, result: dict) -> TransportResult:
        if not result.get("ok"):
            # Failed to find/confirm on the page: the fallback can't do it.
            raise TransportUnavailable(result.get("error") or f"{action} failed")
        return TransportResult(success=True, action=action, detail=result.get("detail") or {})

    async def like(self, account: Any, activity_urn: str) -> TransportResult:
        result = await self._run("like", account, _LIKE_SCRIPT, {
            "url": _activity_url(activity_urn),
            "like_selectors": _LIKE_BUTTON_SELECTORS,
        })
        return self._to_result("like", result)

    async def comment(self, account: Any, activity_urn: str, text: str) -> TransportResult:
        result = await self._run("comment", account, _COMMENT_SCRIPT, {
            "url": _activity_url(activity_urn),
            "text": text,
            "comment_button_selectors": _COMMENT_BUTTON_SELECTORS,
            "comment_input_selectors": _COMMENT_INPUT_SELECTORS,
            "post_button_selectors": _POST_BUTTON_SELECTORS,
        })
        return self._to_result("comment", result)

    async def fetch_inbox(self, account: Any, since: Any = None) -> TransportResult:
        result = await self._run("fetch_inbox", account, _INBOX_SCRIPT, {
            "url": "https://www.linkedin.com/messaging/",
            "expect": "/messaging",
            "ready_selector": "main",
            "resolve_me": True,
            "url_markers": _INBOX_URL_MARKERS,
        })
        if not result.get("ok"):
            raise TransportUnavailable(result.get("error") or "fetch_inbox failed")
        detail = result.get("detail") or {}
        bodies = detail.get("bodies") or []
        if not bodies:
            raise TransportUnavailable(
                "fetch_inbox: /messaging/ loaded but no conversation payload was captured "
                f"({detail.get('matched', 0)} matching responses seen)"
            )
        return TransportResult(
            success=True,
            action="fetch_inbox",
            detail={
                "shape": "harness-network",
                "conversations": normalize_inbox(bodies, detail.get("me")),
                "captured": [b.get("url") for b in bodies],
            },
        )

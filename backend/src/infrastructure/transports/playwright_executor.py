"""
Real Playwright-driven executor for the ``PlaywrightTransport`` fallback.

Honest scope
------------
Before this file existed, ``get_transport()`` never passed a
``playwright_executor`` anywhere in this codebase, so the Playwright fallback
raised "no playwright executor bound" for every action, every time -- found
live (2026-09-25) via a real account's ``fetch_inbox`` failing on the mobile
transport with no working backup at all.

The obvious place to get a *working* executor looked like
``InteractionAgent``/``AccountManagerAgent`` in ``src/agents/core/`` -- the
module docstring on :class:`PlaywrightTransport` literally says it wraps
"the existing, working browser automation" there. It doesn't work: that
class's ``_get_or_create_session`` depends on ``_wait_for_response``, which
is a stub that sleeps until timeout and always returns ``None`` (see the
comment in that method -- "simplified version... implement proper response
tracking"). Every interaction it processes fails at the "get a session" step
before any browser action runs. That subsystem also uses an entirely
different account model (``LinkedInAccount`` with Fernet-encrypted
email/password and Playwright-native cookie lists) than the one the rest of
this app uses (``account.auth_blob``, an ``li_at``/``JSESSIONID`` pair) -- two
parallel account systems that were never reconciled.

So this class owns its own minimal browser/context lifecycle instead, built
against the account model the rest of the app actually uses (same
``auth_blob`` shape ``mobile.py`` reads). ``like`` and ``comment`` are
implemented for real, with selector lists ported from
``InteractionAgent._execute_like_playwright`` / ``_execute_comment_playwright``
-- reusing already-written selector guesses rather than inventing new ones,
but note those were themselves never confirmed against a live account either.

``follow`` and ``connect`` are deliberately NOT implemented here: both need a
navigable profile URL resolved from a bare member URN, and the only clean way
to get one is calling back into the mobile transport this class is supposed
to be the fallback FOR -- circular, so left undone rather than guessed.
``PlaywrightTransport`` already reports "playwright executor lacks {action}"
for a method that doesn't exist, which is the honest behavior here, not a
silent no-op.

Verification status: a chromium browser launches and a context accepts these
cookies (checked directly, see the module's own smoke-test note in
CONNECTING_AN_ACCOUNT.md once someone runs it against a real account) -- but
nothing here has run against a real, logged-in LinkedIn session. Treat every
selector list below the same way ``GQL_PROFILE_RESOLVE_QUERY`` in
``mobile.py`` treats its captured query hash: current as of when it was
written, needs re-confirming against a live session before anyone trusts it
in a real go-live run.
"""

from __future__ import annotations

import random
from typing import Any, Optional

from src.infrastructure.transports.base import TransportResult, TransportUnavailable
from src.infrastructure.transports.mobile import parse_auth_blob

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
    'button:has-text("Post")',
]


def _activity_url(activity_urn: str) -> str:
    """
    A post's activity URN navigates directly via LinkedIn's public
    ``/feed/update/<urn>/`` URL scheme -- the same shape LinkedIn's own
    "Copy link to post" feature generates, so this one (unlike a profile
    URL from a bare member URN) doesn't need any account-specific lookup.
    """
    urn = activity_urn if str(activity_urn).startswith("urn:") else f"urn:li:activity:{activity_urn}"
    return f"https://www.linkedin.com/feed/update/{urn}/"


async def _click_first_match(page, selectors, timeout=5000):
    for selector in selectors:
        try:
            element = await page.wait_for_selector(selector, timeout=timeout)
        except Exception:
            continue
        if element:
            return element
    return None


class BrowserExecutor:
    """
    Injected into :class:`PlaywrightTransport` as its ``executor``. Owns a
    lazily-launched Chromium instance; each call gets its own short-lived
    context (cookies only carry the session, nothing else needs to persist
    between calls).
    """

    def __init__(self, headless: bool = True, playwright_factory=None):
        self._headless = headless
        # Injectable for tests -- a zero-arg async callable returning a
        # Playwright Browser-like object. Defaults to a real chromium launch.
        self._playwright_factory = playwright_factory
        self._playwright = None
        self._browser = None

    async def _ensure_browser(self):
        if self._browser is not None:
            return self._browser
        if self._playwright_factory is not None:
            self._browser = await self._playwright_factory()
            return self._browser

        from playwright.async_api import async_playwright  # lazy: tests never hit this

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self._headless)
        return self._browser

    async def close(self):
        """Release the shared browser. Safe to call even if never launched."""
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    async def _new_page(self, account: Any):
        browser = await self._ensure_browser()
        creds = parse_auth_blob(getattr(account, "auth_blob", None))
        if not creds.get("li_at"):
            raise TransportUnavailable("account has no li_at session cookie")

        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        cookies = [{"name": "li_at", "value": creds["li_at"], "domain": ".linkedin.com", "path": "/"}]
        if creds.get("jsessionid"):
            cookies.append(
                {
                    "name": "JSESSIONID",
                    "value": f'"{creds["jsessionid"]}"',
                    "domain": ".linkedin.com",
                    "path": "/",
                }
            )
        await context.add_cookies(cookies)
        page = await context.new_page()
        return context, page

    async def like(self, account: Any, activity_urn: str) -> TransportResult:
        context, page = await self._new_page(account)
        try:
            await page.goto(_activity_url(activity_urn), wait_until="networkidle")
            await page.wait_for_timeout(random.randint(2000, 4000))

            button = await _click_first_match(page, _LIKE_BUTTON_SELECTORS)
            if not button:
                raise TransportUnavailable("like: no matching like button found on the page")
            if (await button.get_attribute("aria-pressed")) == "true":
                return TransportResult(success=True, action="like", detail={"already_liked": True})
            await button.click()
            await page.wait_for_timeout(random.randint(1000, 2000))
            return TransportResult(success=True, action="like")
        finally:
            await page.close()
            await context.close()

    async def comment(self, account: Any, activity_urn: str, text: str) -> TransportResult:
        context, page = await self._new_page(account)
        try:
            await page.goto(_activity_url(activity_urn), wait_until="networkidle")
            await page.wait_for_timeout(random.randint(2000, 4000))

            comment_button = await _click_first_match(page, _COMMENT_BUTTON_SELECTORS)
            if not comment_button:
                raise TransportUnavailable("comment: no comment button found on the page")
            await comment_button.click()
            await page.wait_for_timeout(random.randint(1000, 2000))

            comment_input = await _click_first_match(page, _COMMENT_INPUT_SELECTORS)
            if not comment_input:
                raise TransportUnavailable("comment: no comment input found on the page")
            await comment_input.click()
            await comment_input.type(text, delay=40)

            post_button = await _click_first_match(page, _POST_BUTTON_SELECTORS)
            if not post_button:
                raise TransportUnavailable("comment: no post/submit button found on the page")
            await post_button.click()
            await page.wait_for_timeout(random.randint(2000, 3000))
            return TransportResult(success=True, action="comment")
        finally:
            await page.close()
            await context.close()

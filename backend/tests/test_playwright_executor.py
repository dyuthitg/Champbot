"""
Tests for BrowserExecutor -- the real Playwright fallback wired into
get_transport(). These use fake Page/Context/Browser doubles (no real
browser launch, no network), the same way test_transports.py fakes the
Voyager HTTP session. What's verified: the click/selector-fallthrough
logic, the cookie shape built from auth_blob, and the honest failure modes.
What's NOT verified by these tests, and can't be from here: whether the
selector strings themselves still match LinkedIn's real, current DOM --
see playwright_executor.py's module docstring.
"""

import types

import pytest

from src.infrastructure.transports.base import TransportUnavailable
from src.infrastructure.transports.playwright_executor import (
    BrowserExecutor,
    _activity_url,
)


def _account(auth_blob=None):
    return types.SimpleNamespace(id="acct-1", auth_blob=auth_blob)


class FakeElement:
    def __init__(self, aria_pressed=None):
        self._aria_pressed = aria_pressed
        self.clicked = False
        self.typed = None

    async def get_attribute(self, name):
        return self._aria_pressed if name == "aria-pressed" else None

    async def click(self):
        self.clicked = True

    async def type(self, text, delay=None):
        self.typed = text


class FakePage:
    def __init__(self, elements_by_selector=None):
        self.elements_by_selector = elements_by_selector or {}
        self.goto_calls = []
        self.closed = False

    async def goto(self, url, wait_until=None):
        self.goto_calls.append(url)

    async def wait_for_timeout(self, ms):
        pass

    async def wait_for_selector(self, selector, timeout=None):
        if selector in self.elements_by_selector:
            return self.elements_by_selector[selector]
        raise TimeoutError(f"no element for {selector}")

    async def close(self):
        self.closed = True


class FakeContext:
    def __init__(self, page):
        self._page = page
        self.cookies_added = None
        self.closed = False

    async def add_cookies(self, cookies):
        self.cookies_added = cookies

    async def new_page(self):
        return self._page

    async def close(self):
        self.closed = True


class FakeBrowser:
    def __init__(self, page):
        self._page = page
        self.contexts = []

    async def new_context(self, **kwargs):
        ctx = FakeContext(self._page)
        self.contexts.append(ctx)
        return ctx


def _executor_for(page):
    browser = FakeBrowser(page)

    async def factory():
        return browser

    return BrowserExecutor(playwright_factory=factory), browser


async def test_activity_url_accepts_bare_id_or_full_urn():
    assert _activity_url("urn:li:activity:12345") == "https://www.linkedin.com/feed/update/urn:li:activity:12345/"
    assert _activity_url("12345") == "https://www.linkedin.com/feed/update/urn:li:activity:12345/"


async def test_like_clicks_first_matching_button():
    page = FakePage({"button[aria-label*=\"Like\"]": FakeElement(aria_pressed="false")})
    executor, _ = _executor_for(page)

    result = await executor.like(_account("li_at_value"), "urn:li:activity:1")

    assert result.success
    assert page.elements_by_selector['button[aria-label*="Like"]'].clicked
    assert page.goto_calls == ["https://www.linkedin.com/feed/update/urn:li:activity:1/"]


async def test_like_is_a_noop_when_already_liked():
    liked_button = FakeElement(aria_pressed="true")
    page = FakePage({"button[aria-label*=\"Like\"]": liked_button})
    executor, _ = _executor_for(page)

    result = await executor.like(_account("li_at_value"), "urn:li:activity:1")

    assert result.success
    assert result.detail == {"already_liked": True}
    assert liked_button.clicked is False


async def test_like_raises_when_no_button_matches():
    page = FakePage({})  # nothing matches any selector
    executor, _ = _executor_for(page)

    with pytest.raises(TransportUnavailable, match="no matching like button"):
        await executor.like(_account("li_at_value"), "urn:li:activity:1")


async def test_like_requires_a_session_cookie_before_touching_the_browser():
    executor, browser = _executor_for(FakePage({}))

    with pytest.raises(TransportUnavailable, match="no li_at session cookie"):
        await executor.like(_account(auth_blob=None), "urn:li:activity:1")

    # Never even opened a context -- fails fast on the missing credential.
    assert browser.contexts == []


async def test_comment_full_flow_types_and_submits():
    page = FakePage(
        {
            'button[aria-label*="Comment"]': FakeElement(),
            'div[contenteditable="true"][role="textbox"]': FakeElement(),
            'button[aria-label="Post comment"]': FakeElement(),
        }
    )
    executor, _ = _executor_for(page)

    result = await executor.comment(_account("li_at_value"), "urn:li:activity:1", "nice post")

    assert result.success
    assert page.elements_by_selector['div[contenteditable="true"][role="textbox"]'].typed == "nice post"
    assert page.elements_by_selector['button[aria-label="Post comment"]'].clicked


async def test_comment_raises_when_input_box_never_appears():
    page = FakePage({'button[aria-label*="Comment"]': FakeElement()})  # no input box mapped
    executor, _ = _executor_for(page)

    with pytest.raises(TransportUnavailable, match="no comment input found"):
        await executor.comment(_account("li_at_value"), "urn:li:activity:1", "nice post")


async def test_cookies_built_from_auth_blob_include_jsessionid_when_present():
    page = FakePage({"button[aria-label*=\"Like\"]": FakeElement(aria_pressed="false")})
    executor, browser = _executor_for(page)

    await executor.like(
        _account({"li_at": "the-li-at", "jsessionid": "the-jsession"}), "urn:li:activity:1"
    )

    cookies = browser.contexts[0].cookies_added
    names = {c["name"] for c in cookies}
    assert names == {"li_at", "JSESSIONID"}
    li_at = next(c for c in cookies if c["name"] == "li_at")
    assert li_at["value"] == "the-li-at"
    assert li_at["domain"] == ".linkedin.com"

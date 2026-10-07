"""
Tests for the transport scaffold: fingerprint stability, composite routing
(mobile -> Playwright fallback), and the Playwright executor adapter.
"""

import types

import pytest

from src.infrastructure.api_client import CompositeTransport, get_transport
from src.infrastructure.transports.base import (
    LinkedInTransport,
    TransportChallenge,
    TransportResult,
    TransportUnavailable,
)
from src.infrastructure.transports.fingerprints import generate_fingerprint
from src.infrastructure.transports.mobile import MobileAPITransport
from src.infrastructure.transports.playwright import PlaywrightTransport

# asyncio_mode=auto (pytest.ini) auto-marks async tests; no module-wide mark so
# the sync fingerprint tests aren't flagged.


def _account(account_id="acct-1"):
    return types.SimpleNamespace(
        id=account_id, auth_blob=None, device_fingerprint=None, proxy=None
    )


# --- Fingerprints ---

def test_fingerprint_is_stable_per_account():
    a = generate_fingerprint("acct-123")
    b = generate_fingerprint("acct-123")
    assert a == b
    assert generate_fingerprint("acct-999") != a


def test_fingerprint_has_required_fields():
    fp = generate_fingerprint("acct-123")
    for key in ("platform", "user_agent", "device_id", "tls_impersonate", "app_version"):
        assert fp.get(key)
    assert fp["platform"] in ("android", "ios")


def test_forced_platform():
    assert generate_fingerprint("x", platform="ios")["platform"] == "ios"
    assert generate_fingerprint("x", platform="android")["platform"] == "android"


# --- Fake transports for routing tests ---

class FakeTransport:
    def __init__(self, name, behavior="ok"):
        self.name = name
        self.behavior = behavior
        self.calls = []

    async def like(self, account, activity_urn):
        self.calls.append("like")
        if self.behavior == "unavailable":
            raise TransportUnavailable(f"{self.name} unavailable")
        if self.behavior == "challenge":
            raise TransportChallenge(f"{self.name} challenge")
        if self.behavior == "fail":
            return TransportResult(success=False, action="like", via=self.name, error="failed")
        return TransportResult(success=True, action="like", via=self.name)


async def test_primary_success_skips_fallback():
    primary = FakeTransport("mobile", "ok")
    fallback = FakeTransport("playwright", "ok")
    comp = CompositeTransport(primary, fallback)

    result = await comp.like(_account(), "urn:activity:1")
    assert result.success
    assert result.via == "mobile"
    assert fallback.calls == []  # fallback not invoked


async def test_unavailable_triggers_fallback():
    primary = FakeTransport("mobile", "unavailable")
    fallback = FakeTransport("playwright", "ok")
    comp = CompositeTransport(primary, fallback)

    result = await comp.like(_account(), "urn:activity:1")
    assert result.success
    assert result.via == "playwright"
    assert result.detail["fell_back_from"] == "mobile"
    assert fallback.calls == ["like"]


async def test_challenge_triggers_fallback():
    comp = CompositeTransport(FakeTransport("mobile", "challenge"), FakeTransport("playwright", "ok"))
    result = await comp.like(_account(), "urn:activity:1")
    assert result.success and result.via == "playwright"


async def test_both_unavailable_returns_failure():
    comp = CompositeTransport(
        FakeTransport("mobile", "unavailable"), FakeTransport("playwright", "unavailable")
    )
    result = await comp.like(_account(), "urn:activity:1")
    assert not result.success
    assert result.error


async def test_no_fallback_returns_failure_on_unavailable():
    comp = CompositeTransport(FakeTransport("mobile", "unavailable"), fallback=None)
    result = await comp.like(_account(), "urn:activity:1")
    assert not result.success


async def test_both_failing_reports_the_primary_error_too():
    """
    When both transports fail, the primary's error must survive.

    Until the Playwright executor is bound its failure is always the same
    uninformative sentence. If that were the only thing reported, it would mask
    the Voyager response — which is the one piece of information needed to fix a
    drifted endpoint shape against a live account.
    """
    comp = CompositeTransport(
        FakeTransport("mobile", "unavailable"),
        FakeTransport("playwright", "unavailable"),
    )

    result = await comp.like(_account(), "urn:activity:1")

    assert not result.success
    assert "mobile unavailable" in result.error
    assert "playwright unavailable" in result.error
    assert result.detail["primary_error"] == "mobile unavailable"
    assert result.detail["primary_via"] == "mobile"
    assert result.detail["fallback_error"] == "playwright unavailable"


# --- Mobile scaffold falls back today ---

async def test_mobile_scaffold_signals_unavailable():
    mobile = MobileAPITransport(session_factory=lambda acct: object())
    with pytest.raises(TransportUnavailable):
        await mobile.like(_account(), "urn:activity:1")


# --- Mobile fetch_profile / fetch_activity endpoint shapes ---


class FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body if body is not None else {}

    def json(self):
        return self._body


class FakeVoyagerSession:
    """Returns canned responses keyed by a substring of the requested path."""

    def __init__(self, routes):
        # routes: list of (substring, response); first match wins.
        self.routes = routes
        self.urls = []

    def request(self, method, url, **kwargs):
        self.urls.append(url)
        for substring, response in self.routes:
            if substring in url:
                return response
        return FakeResponse(status_code=404, body={})


def _gql_profile_body(urn="urn:li:fsd_profile:ACoA123", name=("Ada", "Lovelace")):
    # Mirrors the live envelope: resolved URNs under data.data.*, entities at
    # top-level "included".
    return {
        "data": {
            "data": {
                "identityDashProfilesByMemberIdentity": {"*elements": [urn]},
            },
        },
        "included": [
            {
                "$type": "com.linkedin.voyager.dash.identity.profile.Profile",
                "entityUrn": urn,
                "firstName": name[0],
                "lastName": name[1],
                "headline": "Engineer",
            }
        ],
    }


async def test_fetch_profile_uses_gql_member_identity_shape():
    session = FakeVoyagerSession(
        [("queryId=voyagerIdentityDashProfiles.", FakeResponse(body=_gql_profile_body()))]
    )
    mobile = MobileAPITransport(session_factory=lambda acct: session)

    result = await mobile.fetch_profile(_account(), "https://www.linkedin.com/in/ada-lovelace/")

    assert result.success
    assert result.detail["shape"] == "gql-memberIdentity"
    assert result.detail["member_urn"] == "urn:li:fsd_profile:ACoA123"
    assert result.detail["display_name"] == "Ada Lovelace"
    # The handle was extracted from the URL and sent unquoted.
    assert "(memberIdentity:ada-lovelace)" in session.urls[0]


async def test_fetch_profile_falls_back_to_legacy_when_gql_dead():
    session = FakeVoyagerSession(
        [
            ("queryId=", FakeResponse(status_code=400, body={})),
            (
                "/profileView",
                FakeResponse(
                    body={
                        "profile": {
                            "entityUrn": "urn:li:fs_miniProfile:42",
                            "firstName": "Grace",
                            "headline": "Admiral",
                        }
                    }
                ),
            ),
        ]
    )
    mobile = MobileAPITransport(session_factory=lambda acct: session)

    result = await mobile.fetch_profile(_account(), "grace-hopper")

    assert result.success
    assert result.detail["shape"] == "legacy-profileView"
    assert result.detail["member_urn"] == "urn:li:fs_miniProfile:42"


async def test_fetch_profile_unavailable_when_all_shapes_fail():
    session = FakeVoyagerSession([])
    mobile = MobileAPITransport(session_factory=lambda acct: session)

    with pytest.raises(TransportUnavailable) as excinfo:
        await mobile.fetch_profile(_account(), "nobody")

    # Both failures must be reported so drift is diagnosable from the message.
    assert "gql-memberIdentity" in str(excinfo.value)
    assert "HTTP 404" in str(excinfo.value)


async def test_fetch_activity_uses_gql_content_collections_shape():
    body = {
        "included": [
            {
                "$type": "com.linkedin.voyager.dash.creatorprofile."
                "ProfileContentCollectionsComponent",
                "entityUrn": "urn:li:fsd_profileContentCollectionsComponent:1",
            },
            {
                "$type": "com.linkedin.voyager.dash.feed.Post",
                "entityUrn": "urn:li:share:700",
                "commentary": {"text": {"text": "hello world"}},
            },
        ]
    }
    session = FakeVoyagerSession(
        [("queryId=voyagerIdentityDashProfileComponents.", FakeResponse(body=body))]
    )
    mobile = MobileAPITransport(session_factory=lambda acct: session)

    result = await mobile.fetch_activity(_account(), "urn:li:fs_miniProfile:ACoA123")

    assert result.success
    assert result.detail["shape"] == "gql-contentCollections"
    assert result.detail["posts"] == [{"urn": "urn:li:share:700", "text": "hello world"}]
    # The member id is embedded as an fsd_profile URN, URL-encoded.
    assert "profileUrn:urn%3Ali%3Afsd_profile%3AACoA123" in session.urls[0]


async def test_fetch_activity_unavailable_when_all_shapes_fail():
    session = FakeVoyagerSession([])
    mobile = MobileAPITransport(session_factory=lambda acct: session)

    with pytest.raises(TransportUnavailable) as excinfo:
        await mobile.fetch_activity(_account(), "ACoA123")

    assert "legacy-profileUpdatesV2" in str(excinfo.value)


async def test_fetch_inbox_uses_no_keyversion_shape_first():
    session = FakeVoyagerSession(
        [("/messaging/conversations", FakeResponse(body={"elements": [{"id": 1}]}))]
    )
    mobile = MobileAPITransport(session_factory=lambda acct: session)

    result = await mobile.fetch_inbox(_account())

    assert result.success
    assert result.detail["shape"] == "no-keyVersion"
    assert result.detail["conversations"] == [{"id": 1}]
    assert "keyVersion" not in session.urls[0]


async def test_fetch_inbox_retries_transient_500_then_falls_back_to_legacy(monkeypatch):
    monkeypatch.setattr(
        "src.infrastructure.transports.mobile._INBOX_RETRY_DELAY_SECONDS", 0
    )
    # Order matters: the legacy URL also contains "/messaging/conversations",
    # so the more specific route must be checked first (same trick the
    # existing fetch_profile fallback test uses).
    session = FakeVoyagerSession(
        [
            ("keyVersion=LEGACY_INBOX", FakeResponse(body={"elements": [{"id": 2}]})),
            ("/messaging/conversations", FakeResponse(status_code=500, body={})),
        ]
    )
    mobile = MobileAPITransport(session_factory=lambda acct: session)

    result = await mobile.fetch_inbox(_account())

    assert result.success
    assert result.detail["shape"] == "legacy-keyVersion"
    assert result.detail["conversations"] == [{"id": 2}]
    # One retry on the failing shape (2 calls) + one call that succeeds.
    assert len(session.urls) == 3


async def test_fetch_inbox_does_not_retry_a_plain_4xx():
    session = FakeVoyagerSession([])  # everything 404s
    mobile = MobileAPITransport(session_factory=lambda acct: session)

    with pytest.raises(TransportUnavailable) as excinfo:
        await mobile.fetch_inbox(_account())

    assert "no-keyVersion" in str(excinfo.value)
    assert "legacy-keyVersion" in str(excinfo.value)
    # No retries on a 4xx: exactly one call per shape.
    assert len(session.urls) == 2


# --- Playwright executor adapter ---

class FakeExecutor:
    async def like(self, account, activity_urn):
        return TransportResult(success=True, action="like")


async def test_playwright_delegates_to_executor():
    pw = PlaywrightTransport(executor=FakeExecutor())
    result = await pw.like(_account(), "urn:activity:1")
    assert result.success and result.via == "playwright"


async def test_playwright_without_executor_is_unavailable():
    pw = PlaywrightTransport(executor=None)
    with pytest.raises(TransportUnavailable):
        await pw.like(_account(), "urn:activity:1")


# --- Factory ---

async def test_get_transport_composite_by_default(monkeypatch):
    monkeypatch.delenv("MOBILE_TRANSPORT_ENABLED", raising=False)
    t = get_transport(_account())
    assert isinstance(t, CompositeTransport)


async def test_get_transport_playwright_only_when_disabled(monkeypatch):
    monkeypatch.setenv("MOBILE_TRANSPORT_ENABLED", "false")
    t = get_transport(_account(), playwright_executor=FakeExecutor())
    assert isinstance(t, PlaywrightTransport)
    assert isinstance(t, LinkedInTransport)

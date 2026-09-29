"""
Tests for HarnessExecutor -- the browser-harness fallback wired into
get_transport(). A fake runner stands in for the ``browser-harness``
subprocess and a fake-launcher ChromePool stands in for Chrome, so nothing
real runs. What's verified: secrets stay out of script text and telemetry,
result parsing and failure mapping, and that captured messenger payloads
normalize into something outreach.sync actually reads replies from.

What's NOT verified, and can't be from here: whether the selectors and the
messenger payload shape still match LinkedIn's live site -- see
harness_executor.py's module docstring.
"""

import json
import types

import pytest

from src.infrastructure.api_client import CompositeTransport
from src.infrastructure.transports.base import (
    TransportChallenge,
    TransportResult,
    TransportUnavailable,
)
from src.infrastructure.transports.browser import BrowserTransport
from src.infrastructure.transports.chrome_pool import ChromePool
from src.infrastructure.transports.harness_executor import (
    _COMMENT_SCRIPT,
    _INBOX_SCRIPT,
    _LIKE_SCRIPT,
    HarnessExecutor,
    normalize_inbox,
    parse_result,
)
from src.outreach.sync import _inbound_participants

LI_AT = "AQEDAR-secret-li-at-value"
ME = "urn:li:fsd_profile:ACoAAME"
PROSPECT = "urn:li:fsd_profile:ACoAAPROSPECT"
QUIET = "urn:li:fsd_profile:ACoAAQUIET"


class FakeProc:
    returncode = None

    def terminate(self):
        self.returncode = 0

    async def wait(self):
        return 0


def _pool(tmp_path):
    async def launcher(argv):
        return FakeProc()

    async def probe(url):
        return True

    return ChromePool(data_dir=tmp_path, launcher=launcher, probe=probe, chrome_bin="chrome")


def _account(auth_blob=None):
    blob = auth_blob if auth_blob is not None else json.dumps(
        {"li_at": LI_AT, "jsessionid": "ajax:123"}
    )
    return types.SimpleNamespace(id="acct-1", auth_blob=blob, proxy=None)


class FakeRunner:
    def __init__(self, result=None, stdout=None, stderr="", code=0):
        self.stdout = stdout if stdout is not None else (
            "noise\nCHAMP_RESULT " + json.dumps(result) + "\n"
        )
        self.stderr = stderr
        self.code = code
        self.calls = []

    async def __call__(self, script, env, timeout):
        self.calls.append({"script": script, "env": env})
        return self.code, self.stdout, self.stderr


def _executor(tmp_path, runner):
    return HarnessExecutor(_pool(tmp_path), runner=runner, harness_home=tmp_path / "bh")


# --- scripts & plumbing ---

def test_scripts_are_valid_python():
    for script in (_LIKE_SCRIPT, _COMMENT_SCRIPT, _INBOX_SCRIPT):
        compile(script, "<harness-script>", "exec")


def test_parse_result_takes_the_last_result_line():
    out = 'CHAMP_RESULT {"ok": false}\nlog\nCHAMP_RESULT {"ok": true}\n'
    assert parse_result(out) == {"ok": True}
    assert parse_result("nothing here") is None


async def test_secrets_travel_in_env_never_in_script_and_telemetry_is_off(tmp_path, monkeypatch):
    monkeypatch.setenv("BROWSER_USE_API_KEY", "bu-cloud-key")
    monkeypatch.setenv("BU_AUTOSPAWN", "1")
    runner = FakeRunner({"ok": True})

    await _executor(tmp_path, runner).comment(_account(), "urn:li:activity:1", "Great point")

    call = runner.calls[0]
    assert LI_AT not in call["script"]
    assert "Great point" not in call["script"]
    env = call["env"]
    assert env["BH_TELEMETRY"] == "0"
    assert LI_AT in env["CHAMP_COOKIES"]
    assert json.loads(env["CHAMP_ARGS"])["text"] == "Great point"
    assert env["BU_CDP_URL"].startswith("http://127.0.0.1:")
    assert env["BU_NAME"] == "acct-acct-1"
    # A stray cloud key must not let the harness spin up a paid remote browser.
    assert "BROWSER_USE_API_KEY" not in env
    assert "BU_AUTOSPAWN" not in env


async def test_cookie_shape(tmp_path):
    runner = FakeRunner({"ok": True})
    await _executor(tmp_path, runner).like(_account(), "123")

    cookies = json.loads(runner.calls[0]["env"]["CHAMP_COOKIES"])
    by_name = {c["name"]: c for c in cookies}
    assert by_name["li_at"]["value"] == LI_AT
    assert by_name["li_at"]["domain"] == ".linkedin.com"
    assert by_name["JSESSIONID"]["value"] == '"ajax:123"'
    args = json.loads(runner.calls[0]["env"]["CHAMP_ARGS"])
    assert args["url"] == "https://www.linkedin.com/feed/update/urn:li:activity:123/"


async def test_close_also_stops_the_accounts_harness_daemon(tmp_path):
    """The daemon isn't our child process; without this it outlives its Chrome."""
    runner = FakeRunner({"ok": True})
    executor = _executor(tmp_path, runner)
    await executor.like(_account(), "1")

    await executor.close()

    stop = runner.calls[-1]["env"]
    assert stop["CHAMP_STOP_DAEMON"] == "1"
    assert stop["BU_NAME"] == "acct-acct-1"
    assert json.loads(stop["CHAMP_COOKIES"]) == []  # no session on a stop call
    assert executor._pool.handles() == []


async def test_missing_li_at_fails_before_launching_anything(tmp_path):
    runner = FakeRunner({"ok": True})
    executor = _executor(tmp_path, runner)

    with pytest.raises(TransportUnavailable, match="li_at"):
        await executor.like(_account(auth_blob=""), "1")
    assert runner.calls == []
    assert executor._pool.handles() == []


# --- result mapping ---

async def test_like_success(tmp_path):
    result = await _executor(tmp_path, FakeRunner({"ok": True, "detail": {"selector": "x"}})).like(
        _account(), "1"
    )
    assert result.success and result.action == "like"


async def test_page_level_failure_is_unavailable(tmp_path):
    runner = FakeRunner({"ok": False, "error": "like: no matching like button found on the page"})
    with pytest.raises(TransportUnavailable, match="no matching like button"):
        await _executor(tmp_path, runner).like(_account(), "1")


async def test_login_redirect_is_a_challenge(tmp_path):
    runner = FakeRunner({"ok": False, "challenge": True, "error": "LinkedIn redirected to /checkpoint"})
    with pytest.raises(TransportChallenge):
        await _executor(tmp_path, runner).like(_account(), "1")


async def test_crash_without_result_reports_stderr_tail(tmp_path):
    runner = FakeRunner(stdout="", stderr="Traceback...\nRuntimeError: cdp_disconnected", code=1)
    with pytest.raises(TransportUnavailable, match="cdp_disconnected"):
        await _executor(tmp_path, runner).like(_account(), "1")


# --- inbox ---

def _graphql_body():
    return json.dumps({
        "data": {
            "messengerConversationsBySyncToken": {
                "elements": [
                    {
                        "entityUrn": "urn:li:msg_conversation:1",
                        "unreadCount": 1,
                        "conversationParticipants": [
                            {"hostIdentityUrn": ME},
                            {"hostIdentityUrn": PROSPECT},
                        ],
                        "messages": {"elements": [
                            {"sender": {"hostIdentityUrn": ME}},
                            {"sender": {"hostIdentityUrn": PROSPECT}},
                        ]},
                    },
                    {
                        "entityUrn": "urn:li:msg_conversation:2",
                        "unreadCount": 0,
                        "conversationParticipants": [
                            {"hostIdentityUrn": ME},
                            {"hostIdentityUrn": QUIET},
                        ],
                        "messages": {"elements": [
                            {"sender": {"hostIdentityUrn": ME}},
                        ]},
                    },
                ]
            }
        }
    })


def test_normalized_graphql_inbox_feeds_reply_detection():
    conversations = normalize_inbox(
        [{"url": "https://www.linkedin.com/voyager/api/voyagerMessagingGraphQL/graphql",
          "body": _graphql_body()}],
        me="urn:li:fs_miniProfile:ACoAAME",
    )

    # Only the prospect who actually wrote back counts; the viewer's own
    # messages and the person who never answered do not.
    assert _inbound_participants({"conversations": conversations}) == [PROSPECT]


def test_self_is_inferred_when_me_is_unknown():
    conversations = normalize_inbox([{"url": "x/graphql", "body": _graphql_body()}], me=None)
    assert _inbound_participants({"conversations": conversations}) == [PROSPECT]


def test_legacy_rest_payload_passes_through():
    legacy = {"elements": [{"events": [{"from": {"entityUrn": PROSPECT}}]}]}
    conversations = normalize_inbox(
        [{"url": "https://www.linkedin.com/voyager/api/messaging/conversations",
          "body": json.dumps(legacy)}]
    )
    assert _inbound_participants({"conversations": conversations}) == [PROSPECT]


def test_garbage_bodies_are_skipped():
    assert normalize_inbox([{"url": "x", "body": "<html>"}, {"url": "x", "body": None}]) == []


async def test_fetch_inbox_end_to_end(tmp_path):
    runner = FakeRunner({"ok": True, "detail": {
        "me": ME,
        "bodies": [{"url": "https://www.linkedin.com/voyager/api/voyagerMessagingGraphQL/graphql",
                    "body": _graphql_body()}],
    }})

    result = await _executor(tmp_path, runner).fetch_inbox(_account())

    assert result.success
    assert result.detail["shape"] == "harness-network"
    assert _inbound_participants(result.detail) == [PROSPECT]


async def test_fetch_inbox_with_nothing_captured_is_unavailable(tmp_path):
    runner = FakeRunner({"ok": True, "detail": {"me": ME, "bodies": []}})
    with pytest.raises(TransportUnavailable, match="no conversation payload"):
        await _executor(tmp_path, runner).fetch_inbox(_account())


# --- routed through the composite, the way preflight/sync call it ---

class FailingMobile:
    name = "mobile"

    async def fetch_inbox(self, account, since=None):
        raise TransportUnavailable("fetch_inbox failed on all voyager shapes: no-keyVersion: HTTP 500")


async def test_composite_falls_back_to_harness_for_inbox(tmp_path):
    runner = FakeRunner({"ok": True, "detail": {"me": ME, "bodies": [
        {"url": "x/graphql", "body": _graphql_body()}
    ]}})
    composite = CompositeTransport(
        FailingMobile(), BrowserTransport(executor=_executor(tmp_path, runner))
    )

    result = await composite.fetch_inbox(_account())

    assert isinstance(result, TransportResult)
    assert result.success and result.via == "browser"
    assert result.detail["fell_back_from"] == "mobile"
    assert "HTTP 500" in result.detail["fallback_reason"]

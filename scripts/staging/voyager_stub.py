"""
A local stand-in for LinkedIn's Voyager API, for staging runs.

**This is not LinkedIn.** It is a small HTTP server that speaks the same
endpoint paths and the same JSON envelope shapes, so that a staging run
exercises the real transport code — the device fingerprint, the CSRF header,
the cookie jar, the GraphQL query hashes, the dash-then-legacy shape fallback,
and the response parsing — instead of stubbing all of that out behind a fake
transport object. The only thing replaced is the far end of the socket.

What that buys, concretely: a fake transport returns ``TransportResult(success=
True)`` and proves nothing. This makes the transport build a genuine request and
parse a genuine response, which is where the shape bugs actually live.

Every request is recorded to a JSONL file, credentials redacted. That file is
the evidence of what a run actually sent — the demo's receipt.

Run standalone:
    python scripts/staging/voyager_stub.py --port 8799
"""

from __future__ import annotations

import argparse
import json
import re
import threading
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional

# ----------------------------------------------------------------------
# The people this staging account can see
# ----------------------------------------------------------------------
#
# Written to look like real LinkedIn posts on the topics our ICP cares about,
# because the copywriter is a real LLM and generic filler produces generic
# comments — which would make the quality gate look better than it is.

PERSONAS: List[Dict[str, Any]] = [
    {
        "handle": "amaya-reyes-staging",
        "first_name": "Amaya",
        "last_name": "Reyes",
        "headline": "Head of Growth at Northwind — B2B activation and retention",
        "title": "Head of Growth",
        "company": "Northwind",
        "industry": "SaaS",
        "location": "Berlin",
        "post": (
            "We spent six weeks rebuilding onboarding and moved day-7 activation "
            "by four points. The thing that actually moved it wasn't the "
            "checklist — it was deleting the second screen entirely."
        ),
    },
    {
        "handle": "tom-okafor-staging",
        "first_name": "Tom",
        "last_name": "Okafor",
        "headline": "VP of Growth at Loopwell | PLG, activation, net revenue retention",
        "title": "VP of Growth",
        "company": "Loopwell",
        "industry": "Software",
        "location": "London",
        "post": (
            "Net revenue retention is the only number I trust now. Signups flatter "
            "you, logo churn lags, but NRR tells you within a quarter whether the "
            "product is actually worth renewing."
        ),
    },
    {
        "handle": "priya-sharma-staging",
        "first_name": "Priya",
        "last_name": "Sharma",
        "headline": "Growth Lead at BrightMetrics — B2B SaaS, activation",
        "title": "Growth Lead",
        "company": "BrightMetrics",
        "industry": "SaaS",
        "location": "Amsterdam",
        "post": (
            "We cut our signup form from nine fields to two. Conversion went up "
            "40% and, to my surprise, lead quality didn't move at all. The extra "
            "seven fields were buying us nothing but a slower funnel."
        ),
    },
    {
        "handle": "marcus-bell-staging",
        "first_name": "Marcus",
        "last_name": "Bell",
        "headline": "Director of Growth at Segmenta | activation, retention, B2B",
        "title": "Director of Growth",
        "company": "Segmenta",
        "industry": "SaaS",
        "location": "Austin",
        "post": (
            "Most of what gets called a churn problem is a week-two problem. "
            "Nobody builds a reason to come back on day nine, and then we act "
            "surprised at the day-ninety number."
        ),
    },
    {
        "handle": "lena-hoffmann-staging",
        "first_name": "Lena",
        "last_name": "Hoffmann",
        "headline": "Head of Demand Gen at Cloudrise — B2B software",
        "title": "Head of Demand Gen",
        "company": "Cloudrise",
        "industry": "Software",
        "location": "Dublin",
        "post": (
            "Rewriting our empty states was the highest-leverage week of the "
            "quarter. A blank screen that explains what should be there converts "
            "better than any onboarding email we've ever sent."
        ),
    },
    {
        "handle": "sam-taylor-staging",
        "first_name": "Sam",
        "last_name": "Taylor",
        "headline": "Warehouse Supervisor at Logistix",
        "title": "Warehouse Supervisor",
        "company": "Logistix",
        "industry": "Logistics",
        "location": "Leeds",
        # Deliberately off-ICP and with no post: the run should show this person
        # being filtered out rather than quietly disappearing.
        "post": None,
    },
]

OWNER = {
    "handle": "champbot-staging-operator",
    "first_name": "Staging",
    "last_name": "Operator",
    "headline": "Founder at Champions Ranch",
    "member_urn": "urn:li:fs_miniProfile:STAGINGOWNER",
}


def _by_handle(handle: str) -> Optional[dict]:
    handle = (handle or "").strip().strip('"').lower()
    for p in PERSONAS:
        if p["handle"].lower() == handle:
            return p
    return None


def _by_profile_id(profile_id: str) -> Optional[dict]:
    """Targets are stored with member_urn == the handle, so both resolve here."""
    return _by_handle(_strip_urn(profile_id))


def _strip_urn(value: str) -> str:
    value = urllib.parse.unquote(value or "")
    if ":" in value:
        value = value.rsplit(":", 1)[-1]
    return value


def post_urn_for(handle: str) -> str:
    """Stable per-person activity URN, so re-runs are idempotent."""
    digest = abs(hash(handle)) % 10_000_000_000
    return f"urn:li:activity:{7000000000000000000 + digest}"


# ----------------------------------------------------------------------
# Envelope builders — shaped to match what mobile.py actually parses
# ----------------------------------------------------------------------


def me_envelope() -> dict:
    return {
        "plainId": 1234567,
        "miniProfile": {
            "entityUrn": OWNER["member_urn"],
            "firstName": OWNER["first_name"],
            "lastName": OWNER["last_name"],
            "occupation": OWNER["headline"],
            "publicIdentifier": OWNER["handle"],
        },
    }


def profile_envelope(person: dict) -> dict:
    """
    Matches _parse_gql_profile: the URN under
    data.data.identityDashProfilesByMemberIdentity['*elements'], and the
    Profile entity inlined in ``included`` with a $type ending in
    identity.profile.Profile.
    """
    urn = f"urn:li:fsd_profile:{person['handle']}"
    return {
        "data": {
            "data": {
                "identityDashProfilesByMemberIdentity": {"*elements": [urn]}
            }
        },
        "included": [
            {
                "$type": "com.linkedin.voyager.dash.identity.profile.Profile",
                "entityUrn": urn,
                "firstName": person["first_name"],
                "lastName": person["last_name"],
                "headline": person["headline"],
                "publicIdentifier": person["handle"],
            }
        ],
    }


def activity_envelope(person: dict) -> dict:
    """
    Matches _extract_gql_posts: post entities in ``included``, recognised by a
    $type ending in .Post, carrying entityUrn and commentary.text.

    The first element is the section component the parser is supposed to skip —
    included on purpose, so the run proves the skip actually works.
    """
    included: List[dict] = [
        {
            "$type": "com.linkedin.voyager.dash.identity.profile.ProfileComponent",
            "entityUrn": f"urn:li:fsd_profileComponent:{person['handle']}-content",
        }
    ]
    if person.get("post"):
        included.append(
            {
                "$type": "com.linkedin.voyager.dash.feed.Post",
                "entityUrn": post_urn_for(person["handle"]),
                "commentary": {"text": {"text": person["post"]}},
            }
        )
    return {"data": {"data": {}}, "included": included}


def comment_created_envelope(activity_urn: str, text: str) -> dict:
    return {
        "value": {
            "entityUrn": f"urn:li:comment:({activity_urn},{uuid.uuid4().int % 10**12})",
            "commentary": {"text": text},
            "createdAt": int(time.time() * 1000),
        }
    }


# ----------------------------------------------------------------------
# The server
# ----------------------------------------------------------------------

_GQL_PROFILE = "voyagerIdentityDashProfiles"
_GQL_COMPONENTS = "voyagerIdentityDashProfileComponents"

_REDACT_HEADERS = {"cookie", "csrf-token"}


class StubState:
    """Everything the run wants to inspect afterwards."""

    def __init__(self, log_path: Optional[Path] = None):
        self.requests: List[dict] = []
        self.comments: List[dict] = []
        self.log_path = log_path
        self.lock = threading.Lock()
        # Set to an HTTP status to make the next comment attempt fail, so the
        # run can prove the failure path without waiting for a real outage.
        self.fail_comment_with: Optional[int] = None

    def record(self, entry: dict) -> None:
        with self.lock:
            self.requests.append(entry)
            if self.log_path:
                with self.log_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry) + "\n")


def _redact(headers) -> dict:
    out = {}
    for key, value in headers.items():
        low = key.lower()
        if low in _REDACT_HEADERS:
            out[key] = f"<redacted {len(value)} chars>"
        else:
            out[key] = value
    return out


def make_handler(state: StubState):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        # Quiet: the run prints its own progress.
        def log_message(self, fmt, *args):  # noqa: A003
            pass

        # -------------------------------------------------- plumbing
        def _send(self, status: int, payload: Any) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _record(self, body: Any, status: int, note: str = "") -> None:
            state.record(
                {
                    "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "method": self.command,
                    "path": self.path,
                    "status": status,
                    "note": note,
                    "headers": _redact(self.headers),
                    "body": body,
                }
            )

        def _read_body(self) -> Any:
            length = int(self.headers.get("Content-Length") or 0)
            if not length:
                return None
            raw = self.rfile.read(length)
            try:
                return json.loads(raw.decode("utf-8"))
            except Exception:
                return raw.decode("utf-8", "replace")

        # -------------------------------------------------- routes
        def do_GET(self):  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            path, query = parsed.path, parsed.query

            if path.endswith("/voyager/api/me"):
                self._record(None, 200, "whoami")
                return self._send(200, me_envelope())

            if path.endswith("/voyager/api/graphql"):
                return self._graphql(query)

            # Legacy REST shapes: answered 410, exactly as the real API now
            # does for most sessions. The transport is supposed to try the
            # modern shape first and only reach these on failure -- if these
            # ever show up in the recorded log on a green run, the ordering
            # has regressed.
            if "/identity/profiles/" in path or "/identity/profileUpdatesV2" in path:
                self._record(None, 410, "legacy shape (gone)")
                return self._send(410, {"status": 410, "message": "Gone"})

            self._record(None, 404, "unrouted")
            return self._send(404, {"status": 404, "message": "not found"})

        def do_POST(self):  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            path, query = parsed.path, parsed.query
            body = self._read_body()

            if "normComments" in path or "NormComments" in path:
                return self._comment(path, query, body)

            self._record(body, 404, "unrouted")
            return self._send(404, {"status": 404, "message": "not found"})

        # -------------------------------------------------- handlers
        def _graphql(self, query: str) -> None:
            params = urllib.parse.parse_qs(query)
            query_id = (params.get("queryId") or [""])[0]
            variables = (params.get("variables") or [""])[0]

            if query_id.startswith(_GQL_PROFILE):
                match = re.search(r"memberIdentity:([^,)]+)", variables)
                person = _by_handle(match.group(1)) if match else None
                if not person:
                    self._record(None, 404, "profile not found")
                    return self._send(404, {"status": 404})
                self._record(None, 200, f"fetch_profile {person['handle']}")
                return self._send(200, profile_envelope(person))

            if query_id.startswith(_GQL_COMPONENTS):
                match = re.search(r"profileUrn:([^,)]+)", variables)
                person = _by_profile_id(match.group(1)) if match else None
                if not person:
                    self._record(None, 404, "activity: profile not found")
                    return self._send(404, {"status": 404})
                self._record(None, 200, f"fetch_activity {person['handle']}")
                return self._send(200, activity_envelope(person))

            # An unknown queryId is what a rotated query hash looks like from
            # our side: HTTP 400, which sends the transport to its fallback.
            self._record(None, 400, f"unknown queryId {query_id}")
            return self._send(400, {"status": 400, "message": "unknown query"})

        def _comment(self, path: str, query: str, body: Any) -> None:
            if state.fail_comment_with:
                status = state.fail_comment_with
                state.fail_comment_with = None
                self._record(body, status, "forced failure")
                return self._send(status, {"status": status})

            params = urllib.parse.parse_qs(query)
            thread = urllib.parse.unquote((params.get("threadUrn") or [""])[0])
            text = ""
            if isinstance(body, dict):
                text = ((body.get("commentary") or {}).get("text")) or ""

            if not thread or not text:
                self._record(body, 422, "comment missing thread or text")
                return self._send(422, {"status": 422, "message": "bad comment"})

            shape = "dash" if "socialDashNormComments" in path else "legacy"
            with state.lock:
                state.comments.append(
                    {"activity_urn": thread, "text": text, "shape": shape}
                )
            self._record(body, 201, f"comment posted via {shape}")
            return self._send(201, comment_created_envelope(thread, text))

    return Handler


class VoyagerStub:
    """Context manager that runs the stub on a background thread."""

    def __init__(self, port: int = 0, log_path: Optional[Path] = None):
        self.state = StubState(log_path=log_path)
        self._server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(self.state))
        self.port = self._server.server_address[1]
        self._thread: Optional[threading.Thread] = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/voyager/api"

    def start(self) -> "VoyagerStub":
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        if self._thread:
            self._thread.join(timeout=5)

    def __enter__(self) -> "VoyagerStub":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8799)
    parser.add_argument("--log", default="staging_run/voyager_requests.jsonl")
    args = parser.parse_args()

    log = Path(args.log)
    log.parent.mkdir(parents=True, exist_ok=True)
    stub = VoyagerStub(port=args.port, log_path=log).start()
    print(f"Voyager stub on {stub.base_url}  (logging to {log})")
    print("This is NOT LinkedIn. Ctrl-C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stub.stop()

"""
The whole loop, end to end, on a staging account:

    connect -> scrape -> generate -> flag -> review -> approve -> post

Every stage runs the real product code. The LLM is the real OpenRouter model,
the quality gate is the real gate, the queue is read through the same API route
the UI calls, and the comment is sent by the real Voyager transport building a
real HTTP request.

The one thing that is not real is the far end of that request: it goes to
``scripts/staging/voyager_stub.py``, a local server that speaks Voyager's shapes
and records what it received, instead of to linkedin.com. That is the honest
boundary of this run, and it is deliberate -- see WEEK2_REPORT.md. Nothing in
this repo has ever been validated against a live LinkedIn session.

    python scripts/staging_run.py --dry-run    # everything except the post
    python scripts/staging_run.py              # including the post

Writes staging_run/ : the database, the recorded Voyager traffic, and a
transcript of the run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

OUT_DIR = REPO / "staging_run"
DB_PATH = OUT_DIR / "staging.db"
VOYAGER_LOG = OUT_DIR / "voyager_requests.jsonl"
TRANSCRIPT = OUT_DIR / "transcript.md"

# --- Environment, before anything from src is imported -----------------
OUT_DIR.mkdir(exist_ok=True)
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + str(DB_PATH).replace("\\", "/")
os.environ.setdefault("ALLOW_INSECURE_DEV_ENCRYPTION", "true")
# The mobile transport is the point of this run; never silently fall back to a
# browser we aren't driving.
os.environ["MOBILE_TRANSPORT_ENABLED"] = "true"

# Load .env so the run uses the real LLM rather than the template fallback.
_env = REPO / ".env"
if _env.exists():
    for line in _env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

from scripts.staging.voyager_stub import PERSONAS, VoyagerStub  # noqa: E402


# ----------------------------------------------------------------------
# Transcript
# ----------------------------------------------------------------------

class Log:
    """Prints as it goes and keeps a transcript, so the run is reviewable."""

    def __init__(self, path: Path):
        self.path = path
        self.lines: list = []
        self.breaks: list = []
        self.t0 = time.time()

    def stage(self, name: str) -> None:
        self._write("")
        self._write(f"## {name}")

    def say(self, text: str = "") -> None:
        self._write(text)

    def item(self, text: str) -> None:
        self._write(f"- {text}")

    def broke(self, where: str, what: str, detail: str = "") -> None:
        """A break. Recorded, never swallowed -- the break list is the point."""
        self.breaks.append({"stage": where, "what": what, "detail": detail})
        self._write(f"- **BROKE — {where}:** {what}")
        if detail:
            self._write(f"  `{detail.strip().splitlines()[-1][:300]}`")

    def _write(self, text: str) -> None:
        stamp = f"{time.time() - self.t0:6.1f}s"
        print(f"[{stamp}] {text}" if text else "")
        self.lines.append(text)

    def save(self) -> None:
        header = [
            "# Staging run transcript",
            "",
            f"Run at {datetime.now(timezone.utc).isoformat(timespec='seconds')}.",
            "",
            "LinkedIn calls went to the local Voyager stub, not to linkedin.com.",
            "",
        ]
        self.path.write_text("\n".join(header + self.lines) + "\n", encoding="utf-8")


# ----------------------------------------------------------------------
# The run
# ----------------------------------------------------------------------

async def run(dry_run: bool, log: Log) -> int:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from src.database.models import Base, import_all_models

    import_all_models()
    engine = create_async_engine(os.environ["DATABASE_URL"], future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        account, icp = await stage_connect(db, log)
        if account is None:
            return 1
        await stage_scrape(db, account, log)
        created = await stage_generate(db, account, icp, log)
        queue = await stage_flag(db, account, log)
        chosen = await stage_review(db, account, queue, log)
        if chosen is None:
            return 1
        await stage_approve(db, chosen, log)
        stage_second_opinion(chosen, log)
        await stage_post(db, chosen, dry_run, log)

    await engine.dispose()
    return 0


async def stage_connect(db, log: Log):
    """Connect the staging account -- a real whoami through the transport."""
    log.stage("1. Connect the staging account")

    from src.accounts.schemas import AccountConnect
    from src.accounts.service import connect_account
    from src.targeting.models import ICPProfile
    from src.tenancy.models import Organization, User, UserRole
    from src.warmup import planner as warmup_planner
    from src.warmup import program as warmup_program

    org = Organization(id=uuid.uuid4(), clerk_org_id=None, name="Staging Org")
    db.add(org)
    await db.flush()
    user = User(
        id=uuid.uuid4(),
        clerk_user_id="staging-operator",
        org_id=org.id,
        email="staging@championsmail.com",
        role=UserRole.OWNER,
    )
    db.add(user)
    await db.flush()

    try:
        account = await connect_account(
            db,
            org_id=str(org.id),
            user_id=str(user.id),
            payload=AccountConnect(
                li_at="staging" + "0" * 36,
                jsessionid="ajax:1234567890123456789",
                label="Staging Operator",
                mode="outreach",
            ),
        )
    except Exception as exc:
        log.broke("connect", f"connect_account raised {type(exc).__name__}", traceback.format_exc())
        return None, None

    if account.status != "active":
        log.broke("connect", f"account came back {account.status}", str(account.last_error))
        return None, None

    log.item(f"whoami verified: **{account.display_name}** ({account.linkedin_member_urn})")

    # A brand-new account is in warm-up and may not comment. This is a staging
    # account standing in for one with real history, so it is promoted
    # explicitly -- the same call the warm-up API exposes, not a bypass.
    warmup_planner.set_stage(account, warmup_program.FINAL_STAGE)
    caps = dict(account.daily_caps or {})
    caps["active_hours"] = [0, 24]
    account.daily_caps = caps

    icp = ICPProfile(
        id=uuid.uuid4(),
        org_id=org.id,
        account_id=account.id,
        name="SaaS growth leaders",
        titles=["head of growth", "vp of growth", "growth lead", "director of growth", "head of demand gen"],
        seniorities=["head", "vp", "director", "lead"],
        industries=["saas", "software"],
        keywords=["b2b", "activation", "retention"],
        excluded_keywords=["recruiter", "student"],
        excluded_titles=["intern"],
        locations=[],
        value_proposition="I help B2B SaaS teams fix activation drop-off.",
        relevance_floor=60,
        is_active=True,
    )
    db.add(icp)
    account.active_icp_id = icp.id
    await db.commit()
    log.item(f"ICP active: {icp.name} (relevance floor {icp.relevance_floor})")
    return account, icp


async def stage_scrape(db, account, log: Log) -> None:
    """
    Scrape: hand the system a list of handles and let it find out who they are
    and what they said. Both halves are new as of today -- see
    src/targeting/discover.py.
    """
    log.stage("2. Scrape — resolve the people and find their posts")

    from src.targeting import discover
    from src.targeting.schemas import TargetImportItem
    from src.targeting.service import import_targets

    # The realistic input: a column of profile URLs and nothing else.
    items = [
        TargetImportItem(
            profile_url=f"https://www.linkedin.com/in/{p['handle']}",
            title=p["title"],
            company=p["company"],
            industry=p["industry"],
            location=p["location"],
            source="staging-list",
        )
        for p in PERSONAS
    ]
    created, duplicates = await import_targets(
        db,
        org_id=str(account.org_id),
        account_id=str(account.id),
        items=items,
        icp=None,  # scored after enrichment: a headline we don't have yet can't score
    )
    log.item(f"imported {len(created)} handles ({duplicates} duplicates skipped)")

    try:
        profiles = await discover.refresh_profiles(db, account, targets=created)
    except Exception as exc:
        log.broke("scrape/profiles", f"refresh_profiles raised {type(exc).__name__}", traceback.format_exc())
        return
    log.item(
        f"fetch_profile: checked {profiles['checked']}, filled in {profiles['updated']}, "
        f"failed {profiles['failed']}"
    )
    for err in profiles["errors"]:
        log.item(f"  · {err}")

    try:
        posts = await discover.refresh_posts(db, account, targets=created)
    except Exception as exc:
        log.broke("scrape/posts", f"refresh_posts raised {type(exc).__name__}", traceback.format_exc())
        return
    log.item(
        f"fetch_activity: checked {posts['checked']}, found a post for {posts['updated']}, "
        f"no post {posts['no_posts']}, failed {posts['failed']}"
    )
    for err in posts["errors"]:
        log.item(f"  · {err}")

    # Score now that the headlines are real. Scoring on import would have run
    # against blank headlines and put everyone below the floor.
    from src.targeting.models import TargetStatus
    from src.targeting.scoring import score_target

    icp = await _active_icp(db, account)
    for target in created:
        result = score_target(target, icp)
        target.relevance_score = result.score
        target.relevance_reasons = result.reasons
        target.status = TargetStatus.SKIPPED if result.excluded else TargetStatus.SCORED
    await db.commit()

    for target in sorted(created, key=lambda t: t.relevance_score or 0, reverse=True):
        context = target.context or {}
        has_post = "post" if context.get("post_urn") else "no post"
        log.item(
            f"  {target.full_name or target.public_id} — score {target.relevance_score}, {has_post}"
        )


async def stage_generate(db, account, icp, log: Log):
    """Generate: the real copywriter against the real model."""
    log.stage("3. Generate — draft a comment for each strong match")

    from src.outreach import suggest as engine

    try:
        result = await engine.generate_suggestions(db, account, icp)
    except Exception as exc:
        log.broke("generate", f"generate_suggestions raised {type(exc).__name__}", traceback.format_exc())
        return []

    log.item(result["message"])
    for key, count in (result["skipped"] or {}).items():
        log.item(f"  skipped — {key}: {count}")

    for suggestion in result["created"]:
        log.item(f"  drafted by `{suggestion.generated_by}`: {suggestion.draft_text!r}")

    if not result["created"]:
        log.broke("generate", "no suggestions were created", "nothing to review or post")
    template_only = [s for s in result["created"] if s.generated_by == "template"]
    if template_only:
        log.broke(
            "generate",
            f"{len(template_only)} draft(s) came from the template fallback, not the model",
            "the LLM call failed or no key was loaded; the demo would show canned copy",
        )
    return result["created"]


async def stage_flag(db, account, log: Log):
    """Flag: read the queue through the same route the UI calls."""
    log.stage("4. Flag — read the queue the way the screen reads it")

    from src.api.middleware.clerk import RequestContext
    from src.api.routes.outreach import list_suggestions
    from src.outreach.models import SuggestionStatus
    from src.tenancy.models import User
    from sqlalchemy import select

    user = (await db.execute(select(User).limit(1))).scalar_one()
    ctx = RequestContext(
        user_id=str(user.id),
        org_id=str(account.org_id),
        clerk_user_id="staging-operator",
        clerk_org_id=None,
        email=user.email,
        role="owner",
    )
    try:
        listing = await list_suggestions(
            account_id=str(account.id),
            suggestion_status=SuggestionStatus.PENDING,
            limit=50,
            offset=0,
            ctx=ctx,
            db=db,
        )
    except Exception as exc:
        log.broke("flag", f"list_suggestions raised {type(exc).__name__}", traceback.format_exc())
        return []

    log.item(f"{listing.total} item(s) awaiting review")
    for item in listing.suggestions:
        flags = ", ".join(f"{f.code} {f.label}" for f in item.quality_flags) or "no flags"
        log.item(f"  {item.target.full_name}: quality {item.quality_score}/100 — {flags}")
    return listing.suggestions


async def stage_review(db, account, queue, log: Log):
    """
    Review: pick what a human would pick.

    The rule the operator would apply, applied here: never approve something
    carrying a blocker, and prefer the cleanest draft of the strong matches.
    """
    log.stage("5. Review — choose one to approve")

    if not queue:
        log.broke("review", "the queue was empty", "nothing reached the reviewer")
        return None

    def severity_rank(item):
        """Lower is worse. Advisory-only is not the same as clean: the first
        run of this script picked a four-sentence comment and called it clean,
        because an advisory doesn't block. An operator reading "Too many
        sentences" on the card would not have called it clean either."""
        codes = {f.severity for f in item.quality_flags}
        if "blocker" in codes:
            return 0
        if "warning" in codes:
            return 1
        if "advisory" in codes:
            return 2
        return 3

    ranked = sorted(queue, key=lambda i: (-severity_rank(i), -i.relevance_score))
    clean = [i for i in ranked if severity_rank(i) == 3]
    if not clean:
        log.item("nothing in the queue is completely flag-free; taking the least-flagged one")
    chosen = (clean or ranked)[0]

    log.item(f"approving the comment for **{chosen.target.full_name}**")
    log.item(f"  replying to: {chosen.target.post_text!r}")
    log.item(f"  the comment: {chosen.draft_text!r}")
    log.item(f"  flags: {[f.code for f in chosen.quality_flags] or 'none'}")

    from sqlalchemy import select
    from src.outreach.models import OutreachSuggestion

    return (
        await db.execute(
            select(OutreachSuggestion).where(OutreachSuggestion.id == uuid.UUID(chosen.id))
        )
    ).scalar_one()


async def stage_approve(db, suggestion, log: Log) -> None:
    """Approve: re-checks the gate and schedules a paced send."""
    log.stage("6. Approve — the gate runs again, then it gets a send time")

    from src.outreach import execute as executor

    try:
        suggestion = await executor.approve(db, suggestion, reviewer_id=None)
    except executor.ExecutionBlocked as exc:
        log.broke("approve", "the gate refused the approved copy", str(exc))
        return
    except Exception as exc:
        log.broke("approve", f"approve raised {type(exc).__name__}", traceback.format_exc())
        return

    log.item(f"status: {suggestion.status}")
    log.item(f"scheduled for: {suggestion.scheduled_for}")


def stage_second_opinion(suggestion, log: Log) -> None:
    """
    Grade the approved comment with the August audit's own taxonomy, which was
    written independently of the quality gate and knows nothing about it.

    This stage exists because the first run of this script reported zero breaks
    while approving "That's a fascinating approach, Amaya. It's interesting
    how... Have you noticed any other elements..." -- a validation opener
    wrapped around the exact question shape the audit is named after, scored
    100/100 by the gate. A harness that can ship that and call it green is not
    checking anything. Two graders that disagree is a finding; one grader
    marking its own homework is not.
    """
    log.stage("6b. Second opinion — grade it with the August audit taxonomy")

    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "score_audit", REPO / "scripts" / "score_audit.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    text = suggestion.final_text or suggestion.draft_text or ""
    post = ""
    context = getattr(getattr(suggestion, "target", None), "context", None)
    if isinstance(context, dict):
        post = context.get("post_text") or ""

    tags = module.detect(text, post)
    verdict = module.grade(tags)
    log.item(f"audit taxonomy says: **{verdict}** ({', '.join(tags)})")

    if verdict != "good":
        log.broke(
            "second opinion",
            f"the gate passed a comment the audit taxonomy grades '{verdict}'",
            f"tags: {', '.join(tags)} | text: {text[:160]}",
        )


async def stage_post(db, suggestion, dry_run: bool, log: Log) -> None:
    """Post: the real transport builds a real request."""
    log.stage("7. Post — send it")

    import fakeredis.aioredis
    from src.infrastructure.rate_policy import AccountRateLimiter
    from src.outreach import execute as executor

    if dry_run:
        log.item("DRY RUN — stopping here. Nothing was sent.")
        log.item(f"would send: {suggestion.final_text!r}")
        log.item(f"to activity: {suggestion.subject_urn}")
        return

    limiter = AccountRateLimiter(fakeredis.aioredis.FakeRedis(decode_responses=True))
    try:
        suggestion = await executor.execute_suggestion(
            db, suggestion, rate_limiter=limiter, force=True
        )
    except executor.ExecutionBlocked as exc:
        log.broke("post", "execution was blocked", str(exc))
        return
    except Exception as exc:
        log.broke("post", f"execute_suggestion raised {type(exc).__name__}", traceback.format_exc())
        return

    log.item(f"status: {suggestion.status}")
    log.item(f"sent at: {suggestion.sent_at}")
    if suggestion.status != "sent":
        log.broke("post", f"ended in status {suggestion.status}", str(suggestion.error))


async def _active_icp(db, account):
    from sqlalchemy import select
    from src.targeting.models import ICPProfile

    return (
        await db.execute(
            select(ICPProfile).where(ICPProfile.account_id == account.id).limit(1)
        )
    ).scalar_one()


# ----------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="stop before posting")
    parser.add_argument("--keep-db", action="store_true", help="don't start from a clean database")
    args = parser.parse_args()

    if not args.keep_db and DB_PATH.exists():
        DB_PATH.unlink()
    if VOYAGER_LOG.exists():
        VOYAGER_LOG.unlink()

    log = Log(TRANSCRIPT)
    log.say(f"Mode: {'DRY RUN' if args.dry_run else 'FULL RUN (posts through the stub)'}")

    stub = VoyagerStub(log_path=VOYAGER_LOG).start()
    log.say(f"Voyager stub listening on {stub.base_url} — this is not linkedin.com")

    # Point the real transport at the stub. One constant, patched at runtime;
    # nothing in src/ knows this run exists.
    from src.infrastructure.transports import mobile as mobile_transport

    mobile_transport.VOYAGER_BASE = stub.base_url

    code = 0
    try:
        code = asyncio.run(run(args.dry_run, log))
    except Exception:
        log.broke("run", "the run itself raised", traceback.format_exc())
        code = 1
    finally:
        log.stage("What the stub actually received")
        for entry in stub.state.requests:
            log.item(f"{entry['status']} {entry['method']} {entry['path'][:110]} — {entry['note']}")
        log.stage("Comments the stub accepted")
        if stub.state.comments:
            for comment in stub.state.comments:
                log.item(f"on {comment['activity_urn']} via {comment['shape']}: {comment['text']!r}")
        else:
            log.item("none")

        log.stage("Breaks")
        if log.breaks:
            for b in log.breaks:
                log.item(f"**{b['stage']}** — {b['what']}")
        else:
            log.item("none in this run")

        stub.stop()
        log.save()
        (OUT_DIR / "breaks.json").write_text(json.dumps(log.breaks, indent=2), encoding="utf-8")
        print(f"\ntranscript: {TRANSCRIPT}")
        print(f"voyager traffic: {VOYAGER_LOG}")

    return code


if __name__ == "__main__":
    raise SystemExit(main())

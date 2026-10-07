"""
Scale-up audit run: generate 50+ comments through the REAL pipeline.

Reuses the dry-run harness (fake account, recording transport, template
fallback copywriter) but imports ~58 synthetic prospects, each with a recent
post, so the comment path fires for all of them. Then exports the audit log
(outreach_suggestions) to CSV.

    python scripts/audit_run.py
"""

from __future__ import annotations

import asyncio
import csv
import os
import sys
import uuid

os.environ.setdefault("ALLOW_INSECURE_DEV_ENCRYPTION", "true")

# Load a local .env (OPENROUTER_API_KEY) if present so the real LLM writer runs.
_env = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
if os.path.exists(_env):
    for line in open(_env, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())
else:
    os.environ.pop("OPENROUTER_API_KEY", None)  # no key -> template fallback

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "audit_run.db"))
CSV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "audit_log.csv"))

if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

# Realistic SaaS-growth posts so the comment path has something to react to.
POSTS = [
    "Most activation problems are onboarding problems wearing a costume.",
    "We cut churn 12% by fixing the first-session aha moment, not by adding features.",
    "Your retention curve is flat because week 2 has no reason to exist.",
    "Hiring more SDRs won't fix a leaky activation funnel.",
    "We A/B tested our pricing page for 6 weeks. The winner was the one with fewer words.",
    "Net revenue retention is the only growth metric I actually trust now.",
    "Onboarding checklists are where good intent goes to die.",
    "The best growth loop we built was a cancellation survey that actually got read.",
    "Feature adoption beats feature shipping. Every single time.",
    "We stopped celebrating signups the day we measured day-30 active use.",
    "PLG isn't a motion, it's a promise that the product explains itself.",
    "Your ICP is too broad and it's quietly taxing every campaign you run.",
    "The onboarding email nobody opens is the one that says 'welcome'.",
    "Activation is a team sport — product, marketing and sales all own a piece.",
    "We doubled trial-to-paid by deleting a step, not adding one.",
    "Churn is usually decided in the first 7 days. We just measure it at day 90.",
    "A dashboard nobody checks is a retention problem wearing analytics clothes.",
    "The fastest growth lever we pulled was rewriting empty states.",
    "Your power users are telling you the roadmap. Most teams don't listen.",
    "We replaced our 9-field signup form with 2 fields. Conversion went up 40%.",
]

FIRST = ["Amaya", "Tom", "Lena", "Priya", "Marcus", "Sofia", "Daniel", "Nadia",
         "Ethan", "Ines", "Kofi", "Mei", "Lars", "Aisha", "Diego", "Hana",
         "Viktor", "Zoe", "Omar", "Clara", "Ravi", "Elena", "Jonas", "Tara",
         "Felix", "Maya", "Noah", "Iris", "Sam", "Leah", "Andre", "Yuki",
         "Carmen", "Piotr", "Nina", "Ali", "Rosa", "Karl", "Divya", "Hugo"]
LAST = ["Reyes", "Okafor", "Hoffmann", "Sharma", "Bell", "Rossi", "Kim", "Aziz",
        "Hunt", "Moreau", "Mensah", "Tanaka", "Berg", "Khan", "Silva", "Sato",
        "Petrov", "Lindqvist", "Farah", "Dubois", "Iyer", "Kovacs", "Lund",
        "Nair", "Weber", "Costa", "Park", "Novak", "Osei", "Goldstein",
        "Silveira", "Mori", "Vega", "Nowak", "Larsen", "Hassan", "Ferrara",
        "Brandt", "Nair", "Laurent"]
TITLES = ["Head of Growth", "VP of Growth", "Growth Lead", "Head of Product",
          "Director of Growth", "Growth Marketing Manager", "Head of Demand Gen",
          "VP of Marketing"]
COMPANIES = ["Northwind SaaS", "DataForge", "BrightMetrics", "Loopwell", "Segmenta",
             "Cloudrise", "Metricly", "Flowbase", "Zentro", "Quillio", "Paymera",
             "Insightful", "Nimbly", "Trackr", "Vantia", "Corely", "Driftwell",
             "Signalflow", "Hexaplan", "Lumos"]
INDUSTRIES = ["SaaS", "Software", "B2B Software", "Technology"]
LOCATIONS = ["Berlin", "London", "Amsterdam", "Toronto", "Austin", "Lisbon",
             "Dublin", "Stockholm", "New York", "Singapore"]


async def main() -> None:
    from src.database.models import Base, import_all_models
    from src.accounts.schemas import AccountConnect
    from src.accounts.service import connect_account
    from src.infrastructure.rate_policy import AccountRateLimiter
    from src.outreach import suggest as engine_suggest
    from src.outreach.models import OutreachSuggestion
    from src.targeting.models import ICPProfile, OutreachTarget, TargetStatus
    from src.tenancy.models import Organization, User, UserRole
    from src.warmup import planner as warmup_planner, program as warmup_program
    from sqlalchemy import select
    import fakeredis.aioredis

    # Inline the recording transport here instead of importing it from
    # synthetic_dry_run, whose module top-level pops OPENROUTER_API_KEY.
    from src.infrastructure.transports.base import TransportResult

    class RecordingTransport:
        name = "recording"

        def __init__(self):
            self.calls = []

        async def _record(self, action, *args):
            self.calls.append((action, *args))
            return TransportResult(success=True, action=action, via=self.name,
                                   detail={"recorded": True})

        async def connect(self, account, member_urn, note=None):
            return await self._record("connect", member_urn, note)

        async def send_message(self, account, member_urn, text):
            return await self._record("message", member_urn, text)

        async def comment(self, account, activity_urn, text):
            return await self._record("comment", activity_urn, text)

        async def like(self, account, activity_urn):
            return await self._record("like", activity_urn)

        async def whoami(self, account):
            return TransportResult(
                success=True, action="whoami", via=self.name,
                detail={"member_urn": "urn:li:fs_profile:SYNTHETIC",
                        "public_id": "demo-bot", "display_name": "Demo Operator",
                        "headline": "Founder at Champbot"})

    import_all_models()
    engine = create_async_engine(f"sqlite+aiosqlite:///{DB_PATH}", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        transport = RecordingTransport()
        limiter = AccountRateLimiter(fakeredis.aioredis.FakeRedis(decode_responses=True))

        org = Organization(id=uuid.uuid4(), clerk_org_id=None, name="Audit Org")
        db.add(org)
        await db.flush()
        user = User(id=uuid.uuid4(), clerk_user_id="audit-user", org_id=org.id,
                    email="audit@example.com", role=UserRole.OWNER)
        db.add(user)
        await db.flush()

        account = await connect_account(
            db, org_id=str(org.id), user_id=str(user.id),
            payload=AccountConnect(li_at="synthetic" + "0" * 34,
                                   jsessionid="ajax:0000000000",
                                   label="Audit Operator", mode="outreach"),
            transport=transport,
        )
        caps = dict(account.daily_caps or {})
        caps["active_hours"] = [0, 24]
        caps["tier"] = "aggressive"
        # Audit-only: lift the daily action caps + suggestion budget so all 50+
        # comments generate in one run. In production these caps keep accounts
        # safe; here we only want a large batch of copy to audit.
        for k in ("connect", "message", "comment", "like"):
            caps[k] = {"per_hour": 500, "per_day": 500, "per_week": 2000,
                       "cooldown_seconds": 1}
        caps["suggestion_budget"] = 500
        account.daily_caps = caps
        warmup_planner.set_stage(account, warmup_program.FINAL_STAGE)

        icp = ICPProfile(
            id=uuid.uuid4(), org_id=org.id, account_id=account.id,
            name="SaaS growth leaders",
            titles=["head of growth", "vp of growth", "growth lead"],
            seniorities=["head", "vp", "director"],
            industries=["saas", "software"],
            keywords=["b2b", "activation", "retention"],
            excluded_keywords=["recruiter", "student"],
            excluded_titles=["intern"], locations=[],
            value_proposition="I help B2B SaaS teams fix activation drop-off.",
            relevance_floor=20, is_active=True,
        )
        db.add(icp)
        account.active_icp_id = icp.id
        await db.flush()

        # ~58 prospects, every one with a recent post -> comment path.
        n = 58
        for i in range(n):
            first, last = FIRST[i % len(FIRST)], LAST[i % len(LAST)]
            company = COMPANIES[i % len(COMPANIES)]
            title = TITLES[i % len(TITLES)]
            post = POSTS[i % len(POSTS)]
            db.add(OutreachTarget(
                id=uuid.uuid4(), org_id=org.id, account_id=account.id,
                icp_id=icp.id, status=TargetStatus.NEW, source="csv",
                member_urn=f"urn:li:member:{1000 + i}",
                public_id=f"{first.lower()}-{last.lower()}-{i}",
                full_name=f"{first} {last}", first_name=first,
                title=title, company=company,
                headline=f"{title} at {company} — B2B activation and retention",
                industry=INDUSTRIES[i % len(INDUSTRIES)],
                location=LOCATIONS[i % len(LOCATIONS)],
                context={"post_urn": f"urn:li:activity:{7000 + i}",
                         "post_text": post},
            ))
        await db.commit()
        print(f"[targets] imported {n} synthetic prospects with posts")

        result = await engine_suggest.generate_suggestions(
            db, account, icp, rate_limiter=limiter)
        created = result["created"]
        print(f"[suggest] {result['message']}")

        # Export the audit log: every generated comment/suggestion. Include the
        # target's post_text so the auditor can judge "did the comment engage
        # with what was actually said".
        rows = (await db.execute(
            select(OutreachSuggestion).order_by(OutreachSuggestion.created_at)
        )).scalars().all()
        tgt = {t.id: t for t in (await db.execute(select(OutreachTarget))).scalars().all()}
        with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["id", "action", "status", "target_id", "subject_urn",
                        "relevance_score", "quality_score", "generated_by",
                        "rationale", "quality_warnings", "post_text", "draft_text"])
            for s in rows:
                post = ""
                t = tgt.get(s.target_id)
                if t and isinstance(t.context, dict):
                    post = t.context.get("post_text", "")
                w.writerow([str(s.id), s.action, s.status, str(s.target_id),
                            s.subject_urn, s.relevance_score, s.quality_score,
                            s.generated_by, s.rationale,
                            s.quality_warnings, post, s.draft_text])
        print(f"[export] wrote {len(rows)} rows -> {CSV_PATH}")

    await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

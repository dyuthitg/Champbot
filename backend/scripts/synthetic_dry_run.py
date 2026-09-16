"""
Synthetic dry run: the full pipeline with synthetic data, zero LinkedIn.

Runs the real product code path end to end — connect (fake cookie), synthetic
prospects, scoring, suggestion generation, human approval, paced execution —
with the transport replaced by a recorder and the datastore swapped for a local
SQLite file. Nothing leaves the machine; every row the system writes is the
audit trail this script dumps at the end.

    python scripts/synthetic_dry_run.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

# Must be set before any src imports: dev encryption + local-only db.
os.environ.setdefault("ALLOW_INSECURE_DEV_ENCRYPTION", "true")
os.environ.pop("OPENROUTER_API_KEY", None)  # force the template fallback

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "synthetic_dry_run.db")
DB_PATH = os.path.abspath(DB_PATH)

if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402


class RecordingTransport:
    """Satisfies the LinkedInTransport protocol but never touches the network."""

    name = "recording"

    def __init__(self, fail_with: str | None = None):
        self.calls: list[tuple] = []
        self.fail_with = fail_with

    async def _record(self, action: str, *args):
        from src.infrastructure.transports.base import TransportResult

        self.calls.append((action, *args))
        ok = self.fail_with is None
        return TransportResult(
            success=ok, action=action, via=self.name, error=self.fail_with,
            detail={"recorded": True} if ok else None,
        )

    async def connect(self, account, member_urn, note=None):
        return await self._record("connect", member_urn, note)

    async def send_message(self, account, member_urn, text):
        return await self._record("message", member_urn, text)

    async def comment(self, account, activity_urn, text):
        return await self._record("comment", activity_urn, text)

    async def like(self, account, activity_urn):
        return await self._record("like", activity_urn)

    async def whoami(self, account):
        from src.infrastructure.transports.base import TransportResult

        return TransportResult(
            success=True, action="whoami", via=self.name,
            detail={
                "member_urn": "urn:li:fs_profile:SYNTHETIC",
                "public_id": "demo-bot",
                "display_name": "Demo Operator",
                "headline": "Founder at Champbot",
            },
        )


async def main() -> None:
    from src.database.models import Base, import_all_models

    import_all_models()
    engine = create_async_engine(f"sqlite+aiosqlite:///{DB_PATH}", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        from src.accounts.schemas import AccountConnect
        from src.accounts.service import connect_account
        from src.accounts.models import ConnectedAccount
        from src.infrastructure.rate_policy import AccountRateLimiter
        from src.outreach import execute as executor
        from src.outreach import suggest as engine_suggest
        from src.outreach.models import OutreachSuggestion
        from src.targeting.models import ICPProfile, OutreachTarget, TargetStatus
        from src.tenancy.models import Organization, User, UserRole
        from src.warmup import planner as warmup_planner, program as warmup_program
        from src.warmup.models import AccountActivity

        import fakeredis.aioredis

        transport = RecordingTransport()
        limiter = AccountRateLimiter(fakeredis.aioredis.FakeRedis(decode_responses=True))

        # --- Tenancy --------------------------------------------------------
        org = Organization(id=uuid.uuid4(), clerk_org_id=None, name="Demo Org")
        db.add(org)
        await db.flush()
        user = User(
            id=uuid.uuid4(), clerk_user_id="demo-user", org_id=org.id,
            email="demo@example.com", role=UserRole.OWNER,
        )
        db.add(user)
        await db.flush()

        # --- Connect a fake account: dummy cookie, transport answers whoami --
        account = await connect_account(
            db, org_id=str(org.id), user_id=str(user.id),
            payload=AccountConnect(
                li_at="synthetic" + "0" * 34,
                jsessionid="ajax:0000000000",
                label="Demo Operator", mode="outreach",
            ),
            transport=transport,
        )
        print(f"[connect] account {account.id} -> status={account.status} "
              f"(verified via {account.daily_caps.get('_meta', {}).get('verified_via')})")

        # Demo-only: widen the activity window so the run works at any hour,
        # and graduate the warm-up programme like a fully ramped account.
        caps = dict(account.daily_caps or {})
        caps["active_hours"] = [0, 24]
        account.daily_caps = caps
        warmup_planner.set_stage(account, warmup_program.FINAL_STAGE)

        # --- ICP -------------------------------------------------------------
        icp = ICPProfile(
            id=uuid.uuid4(), org_id=org.id, account_id=account.id,
            name="SaaS growth leaders",
            titles=["head of growth", "vp of growth", "growth lead"],
            seniorities=["head", "vp", "director"],
            industries=["saas", "software"],
            keywords=["b2b", "activation", "retention"],
            excluded_keywords=["recruiter", "student"],
            excluded_titles=["intern"],
            locations=[],
            value_proposition="I help B2B SaaS teams fix activation drop-off.",
            relevance_floor=60, is_active=True,
        )
        db.add(icp)
        account.active_icp_id = icp.id
        await db.flush()

        # --- Synthetic prospects --------------------------------------------
        def target(status=TargetStatus.NEW, context=None, **kw):
            t = OutreachTarget(
                id=uuid.uuid4(), org_id=org.id, account_id=account.id,
                icp_id=icp.id, status=status, source="csv", context=context or {},
                **kw,
            )
            db.add(t)
            return t

        target(member_urn="urn:li:member:001", public_id="amaya-reyes",
               full_name="Amaya Reyes", first_name="Amaya",
               title="Head of Growth", company="Northwind SaaS",
               headline="Head of Growth at Northwind — B2B activation and retention",
               industry="SaaS", location="Berlin")
        target(member_urn="urn:li:member:002", public_id="tom-okafor",
               full_name="Tom Okafor", first_name="Tom",
               title="VP of Growth", company="DataForge",
               headline="VP of Growth, DataForge — scaling B2B retention loops",
               industry="Software", location="London",
               context={"post_urn": "urn:li:activity:777000111",
                        "post_text": "Most activation problems are onboarding problems wearing a costume."})
        target(member_urn="urn:li:member:003", public_id="lena-hoff",
               full_name="Lena Hoffmann", first_name="Lena",
               title="Growth Lead", company="BrightMetrics",
               headline="Growth Lead at BrightMetrics",
               industry="SaaS", location="Amsterdam",
               status=TargetStatus.CONNECTED)  # already a connection -> first message
        target(member_urn="urn:li:member:004", public_id="raj-recruiter",
               full_name="Raj Singh", first_name="Raj",
               title="Head of Growth", company="TalentPool",
               headline="Head of Growth and technical recruiter for SaaS scale-ups",
               industry="SaaS", location="Toronto")  # excluded keyword: recruiter
        target(member_urn="urn:li:member:005", public_id="mia-chen",
               full_name="Mia Chen", first_name="Mia",
               title="Barista", company="Blue Bottle",
               headline="Coffee professional",
               industry="Food & Beverage", location="Portland")  # below the floor

        await db.commit()
        print(f"[targets] imported 5 synthetic prospects: 3 fit, 1 excluded "
              f"(recruiter), 1 below floor (barista)")

        # --- Generate suggestions -------------------------------------------
        result = await engine_suggest.generate_suggestions(
            db, account, icp, rate_limiter=limiter,
        )
        print(f"\n[suggest] {result['message']} (considered={result['considered']}, "
              f"skipped={result['skipped']})")
        created = result["created"]
        for s in created:
            print(f"  - [{s.status}] {s.action} score={s.relevance_score} "
                  f"quality={s.quality_score} via={s.generated_by}")
            print(f"      rationale: {s.rationale}")
            print(f"      draft: {s.draft_text!r}")

        # --- Human approves everything pending -------------------------------
        now = datetime.now(timezone.utc)
        for s in created:
            if s.status == "pending":
                await executor.approve(db, s, reviewer_id=str(user.id), send_at=now)
        print(f"\n[approve] approved {sum(1 for s in created if s.status == 'scheduled')} "
              f"suggestions at {now.isoformat()}")

        # --- Execute the due queue -------------------------------------------
        run = await executor.run_due(
            db, account, transport=transport, rate_limiter=limiter, limit=10,
        )
        print(f"[run_due] sent={len(run['sent'])} blocked={run['blocked']}")
        for call in transport.calls:
            print(f"  transport saw: {call[0]} -> {call[1]} text={str(call[2])[:80]!r}")

        # --- The audit trail --------------------------------------------------
        print("\n" + "=" * 72)
        print("AUDIT LOG (account_activity — one row per attempted action)")
        print("=" * 72)
        ledger = (await db.execute(
            select(AccountActivity).order_by(AccountActivity.created_at)
        )).scalars().all()
        for row in ledger:
            print(f"  {row.created_at}  {row.action:<10} {row.status:<8} "
                  f"stage={row.stage or '-':<8} target={row.target_id} "
                  f"urn={row.subject_urn} detail={row.detail} error={row.error}")

        print("\n" + "=" * 72)
        print("SUGGESTION PIPELINE STATE (outreach_suggestions)")
        print("=" * 72)
        suggestions = (await db.execute(
            select(OutreachSuggestion).order_by(OutreachSuggestion.created_at)
        )).scalars().all()
        for s in suggestions:
            print(f"  {s.action:<8} {s.status:<10} quality={s.quality_score} "
                  f"sent_at={s.sent_at} gt={s.generated_by} error={s.error}")

        print("\n" + "=" * 72)
        print("FUNNEL STATE (outreach_targets)")
        print("=" * 72)
        targets = (await db.execute(select(OutreachTarget))).scalars().all()
        for t in targets:
            print(f"  {t.full_name:<16} status={t.status:<10} "
                  f"score={t.relevance_score} reasons={t.relevance_reasons} "
                  f"invited_at={t.invited_at}")

    await engine.dispose()
    print(f"\n[dry-run] complete — audit DB persisted at: {DB_PATH}")
    print("Inspect it with: sqlite3 synthetic_dry_run.db "
          "'select action,status,stage,subject_urn,detail from account_activity'")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

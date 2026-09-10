"""
Migration tests.

Two things can go wrong with Alembic and both are silent until production:

1. **Drift** — someone edits a model and forgets the migration. The schema the
   tests run against (built by ``create_all``) then stops matching the schema a
   real deploy gets (built by migrations), and everything passes right up until
   the column is missing in production. ``test_migrations_match_models`` runs the
   migrations for real and asks Alembic's own autogenerate comparison whether
   anything is left over. Anything but "no changes" fails.

2. **A data step that was never executed** — 0002 backfills campaigns that
   predate tenancy. That branch runs exactly once per deployment, and by then
   it is too late to find out it was wrong, so both of its paths are exercised
   here.

These are sync tests on purpose: Alembic's env.py owns its event loop, and
nesting that inside pytest-asyncio's would deadlock.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def alembic_config(db_path: Path) -> Config:
    """Alembic configured to run against a throwaway SQLite file."""
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    return config


@pytest.fixture
def db_path(tmp_path) -> Path:
    return tmp_path / "migrations.db"


@pytest.fixture
def sync_engine(db_path):
    """A plain sync engine on the same file, for asserting on the result."""
    engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    yield engine
    engine.dispose()


def test_migrations_match_models(db_path, sync_engine):
    """
    A database built by migrations is identical to one built from the models.

    This is the guard against drift: add a column to a model without a
    migration and this test fails with the missing operation named.
    """
    from src.database.models import Base, import_all_models

    command.upgrade(alembic_config(db_path), "head")
    import_all_models()

    with sync_engine.connect() as conn:
        context = MigrationContext.configure(conn, opts={"compare_type": True})
        diff = compare_metadata(context, Base.metadata)

    assert diff == [], f"models and migrations have drifted apart: {diff}"


def test_downgrade_and_upgrade_round_trip(db_path, sync_engine):
    """head -> base -> head leaves the schema where it started."""
    config = alembic_config(db_path)
    command.upgrade(config, "head")
    command.downgrade(config, "base")

    inspector = sa.inspect(sync_engine)
    remaining = set(inspector.get_table_names()) - {"alembic_version"}
    assert remaining == set(), f"downgrade left tables behind: {remaining}"

    command.upgrade(config, "head")
    assert "campaigns" in sa.inspect(sync_engine).get_table_names()


def _seed_pre_tenancy_campaign(engine, *, with_org: bool) -> uuid.UUID | None:
    """Insert a campaign at the 0001 schema, as AUTO_CREATE_TABLES would have."""
    org_id = uuid.uuid4() if with_org else None
    with engine.begin() as conn:
        if with_org:
            conn.execute(
                sa.text(
                    "INSERT INTO organizations (id, name, plan, settings, created_at, updated_at)"
                    " VALUES (:id, 'Acme', 'free', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"id": str(org_id)},
            )
        conn.execute(
            sa.text(
                "INSERT INTO campaigns"
                " (id, name, status, target_urls, account_ids, actions, priority,"
                "  total_tasks, completed_tasks, failed_tasks, created_at, updated_at)"
                " VALUES (:id, 'Legacy campaign', 'draft', '[]', '[]', '{}', 1,"
                "         0, 0, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"id": str(uuid.uuid4())},
        )
    return org_id


def test_backfill_adopts_orphans_into_the_existing_org(db_path, sync_engine):
    """An unowned campaign is adopted, not destroyed, when an org exists."""
    config = alembic_config(db_path)
    command.upgrade(config, "0001")
    org_id = _seed_pre_tenancy_campaign(sync_engine, with_org=True)

    command.upgrade(config, "0002")

    with sync_engine.connect() as conn:
        rows = conn.execute(sa.text("SELECT name, org_id FROM campaigns")).fetchall()

    assert len(rows) == 1, "the campaign should have survived the migration"
    assert rows[0].name == "Legacy campaign"
    assert str(rows[0].org_id) == str(org_id)


def test_backfill_creates_a_holding_org_when_none_exists(db_path, sync_engine):
    """
    With no organization at all, the migration no longer aborts.

    2026-09-10: an abort here meant the app crashed on every boot until a human
    ran a manual SQL step against production — the healthcheck never got a
    response and the deploy never came up. 0002 still refuses to guess a *real*
    tenant (see test_backfill_adopts_orphans_into_the_existing_org for that
    case, unchanged), but with none available it now creates one clearly-labeled
    holding organization and finishes the deploy, rather than blocking it.
    """
    config = alembic_config(db_path)
    command.upgrade(config, "0001")
    _seed_pre_tenancy_campaign(sync_engine, with_org=False)

    command.upgrade(config, "0002")  # must not raise

    with sync_engine.connect() as conn:
        rows = conn.execute(sa.text("SELECT name, org_id FROM campaigns")).fetchall()
        version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
        orgs = conn.execute(sa.text("SELECT id, name FROM organizations")).fetchall()

    assert version == "0002", "the migration must complete, not stay half-applied"
    assert len(rows) == 1, "the campaign must survive"
    assert rows[0].org_id is not None

    # Exactly one org exists, it owns the orphan, and its name makes it
    # unmistakable that this is not a real tenant.
    assert len(orgs) == 1
    assert str(orgs[0].id) == str(rows[0].org_id)
    assert "auto-created" in orgs[0].name.lower()
    assert "unassigned" in orgs[0].name.lower()


def test_backfill_never_adopts_into_an_existing_real_org_by_accident(db_path, sync_engine):
    """
    The holding-org fallback only ever fires when *zero* organizations exist.

    If even one real organization is present, orphans must still go to it (the
    existing, unchanged behavior) rather than into a new holding org — the
    fallback is for the "nothing to adopt into" case only, never a substitute
    for the oldest-org rule.
    """
    config = alembic_config(db_path)
    command.upgrade(config, "0001")
    org_id = _seed_pre_tenancy_campaign(sync_engine, with_org=True)

    command.upgrade(config, "0002")

    with sync_engine.connect() as conn:
        rows = conn.execute(sa.text("SELECT org_id FROM campaigns")).fetchall()
        org_count = conn.execute(sa.text("SELECT COUNT(*) FROM organizations")).scalar_one()

    assert org_count == 1, "no holding org should be created when a real one exists"
    assert str(rows[0].org_id) == str(org_id)

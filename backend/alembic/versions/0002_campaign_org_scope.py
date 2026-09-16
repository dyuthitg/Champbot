"""Give campaigns an owning organization.

Campaigns predate tenancy in this codebase and had no owner column, which is why
their routes could not be org-scoped: there was nothing to scope them by. This
adds ``org_id`` (required) and ``created_by_user_id`` (optional attribution).

Backfilling rows that never had an owner
----------------------------------------
The column is NOT NULL, so existing rows need a value, and the correct one was
never recorded. The rule here:

* If any organization exists, orphans are assigned to the **oldest** one. In
  every deployment so far that is the only organization, so this is exact rather
  than a guess.
* If **no** organization exists, the migration used to abort outright — there is
  no *real* tenant to guess as the owner, and this migration will still never
  guess one. But an abort here is a deploy that fails on every boot until a
  human runs a manual step against production, and the app never starts in the
  meantime (2026-09-10: this is exactly what happened). So instead it creates
  one explicitly-labeled **holding organization** ("Unassigned pre-tenancy
  data...") and adopts the orphans into *that* — never a real tenant, never a
  guess, and named so nobody mistakes it for one. Whoever finds it should
  reassign those campaigns to their real owner and remove the holding org; nothing
  here does that automatically, because that reassignment is a decision this
  migration still can't make.

This migration never deletes data, and it never invents an owner among *real*
organizations. A wrong delete or a wrong real-tenant guess is unrecoverable; a
holding organization is just a very visible TODO.

At revision 0001 the ``org_id`` column does not exist yet, so every campaign
present is by definition unowned — the pre-check counts rows in ``campaigns``,
which is exactly the orphan count.

Row counts are printed on the adoption path too, so the deploy log records
exactly what happened rather than leaving you to infer it.

Revision ID: 0002
Revises: 0001
"""

import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Decide who owns any orphaned rows *before* changing the schema, so a
    #    holding-org insert (or, on an already-owned database, no insert at
    #    all) is the only write that happens before the DDL below.
    #    org_id does not exist yet, so every campaign here is unowned.
    orphans = conn.execute(sa.text("SELECT COUNT(*) FROM campaigns")).scalar_one()
    owner = None

    if orphans:
        owner = conn.execute(
            sa.text("SELECT id FROM organizations ORDER BY created_at, id LIMIT 1")
        ).scalar_one_or_none()

        if owner is None:
            # No real tenant to adopt these into, and this migration still will
            # not guess one. Park them in an explicit, unmistakably-fake holding
            # organization instead of blocking every future boot on a manual SQL
            # step against production -- see the module docstring.
            owner = str(uuid.uuid4())
            conn.execute(
                sa.text(
                    "INSERT INTO organizations (id, name, plan, settings, created_at, updated_at)"
                    " VALUES (:id, :name, 'free', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {
                    "id": owner,
                    "name": "Unassigned pre-tenancy data (auto-created by migration 0002)",
                },
            )
            print(
                f"[0002] no organization existed to adopt {orphans} pre-tenancy "
                f"campaign(s); created holding organization {owner} for them. "
                "Reassign these campaigns to their real owner, then rename or "
                "remove that organization -- this migration will not do that "
                "part for you."
            )

    # 2. Safe to proceed. Add both columns nullable so existing rows survive the
    #    DDL, then give them the owner found above.
    op.add_column("campaigns", sa.Column("org_id", sa.Uuid(), nullable=True))
    op.add_column("campaigns", sa.Column("created_by_user_id", sa.Uuid(), nullable=True))

    if orphans:
        conn.execute(
            sa.text("UPDATE campaigns SET org_id = :owner WHERE org_id IS NULL"),
            {"owner": owner},
        )
        print(f"[0002] adopted {orphans} pre-tenancy campaign(s) into organization {owner}")

    # 3. Now the column can be required, and the constraints can go on.
    #    Batch mode is required on SQLite (no in-place ALTER) and is a
    #    passthrough on Postgres.
    with op.batch_alter_table("campaigns", schema=None) as batch_op:
        batch_op.alter_column("org_id", existing_type=sa.Uuid(), nullable=False)
        batch_op.create_foreign_key(
            "fk_campaigns_org_id_organizations",
            "organizations",
            ["org_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_campaigns_created_by_user_id_users",
            "users",
            ["created_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_index("ix_campaigns_org_id", "campaigns", ["org_id"], unique=False)
    op.create_index(
        "ix_campaigns_created_by_user_id", "campaigns", ["created_by_user_id"], unique=False
    )


def downgrade() -> None:
    """
    Reversible in schema only.

    Dropping org_id discards which organization each campaign belonged to; the
    rows survive but re-running 0002 afterwards will re-adopt them all into the
    oldest org, which is wrong for anyone who had more than one. Take a backup
    before downgrading a database with real campaigns in it.
    """
    op.drop_index("ix_campaigns_created_by_user_id", table_name="campaigns")
    op.drop_index("ix_campaigns_org_id", table_name="campaigns")

    with op.batch_alter_table("campaigns", schema=None) as batch_op:
        batch_op.drop_constraint("fk_campaigns_created_by_user_id_users", type_="foreignkey")
        batch_op.drop_constraint("fk_campaigns_org_id_organizations", type_="foreignkey")
        batch_op.drop_column("created_by_user_id")
        batch_op.drop_column("org_id")

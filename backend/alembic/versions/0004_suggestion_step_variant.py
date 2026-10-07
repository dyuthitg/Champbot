"""Add outreach_suggestions.step / .variant where a database is missing them.

These two columns (cadence step, copy variant) were added to the model on
Jul 30 (commit ac73d97, the warm-up programme), but 0001_baseline.py already
describes the *current* model shape rather than what was actually run against
production at the time -- its own docstring says it "reproduces exactly what
Base.metadata.create_all produced" as of when it was written, not as of any
specific historical deploy. A database whose ``outreach_suggestions`` table
was created before Jul 30 and was later brought under Alembic with
``alembic stamp`` (marking 0001 applied without running its DDL, the normal
way to adopt Alembic onto an already-existing schema) would be stamped at
0001 while its real columns still predate step/variant. That's exactly the
shape of the live error this migration fixes: every read of
outreach_suggestions failing with ``UndefinedColumnError: column
outreach_suggestions.step does not exist``, in production, right now.

Guarded by an inspector check rather than a bare ``op.add_column`` because
the failure mode being fixed is schema drift of unknown extent -- a database
that already has both columns (any dev/CI database built via
AUTO_CREATE_TABLES from the current models) must not error out on this
migration, and one missing only one of the two must still get the other.

Revision ID: 0004
Revises: 0003
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "outreach_suggestions"


def upgrade() -> None:
    bind = op.get_bind()
    existing = {c["name"] for c in sa.inspect(bind).get_columns(TABLE)}

    with op.batch_alter_table(TABLE, schema=None) as batch_op:
        if "step" not in existing:
            batch_op.add_column(sa.Column("step", sa.String(length=32), nullable=True))
            print(f"[0004] added {TABLE}.step")
        if "variant" not in existing:
            batch_op.add_column(sa.Column("variant", sa.String(length=64), nullable=True))
            print(f"[0004] added {TABLE}.variant")


def downgrade() -> None:
    """
    No-op on purpose.

    A database this migration actually changed something on had step/variant
    missing in the first place -- that is, it was never really at the
    "current model" shape 0001 claims. Dropping the columns on downgrade
    would put it back in the broken state this migration exists to fix,
    for every past and future deploy, not just the one being rolled back.
    """
    pass

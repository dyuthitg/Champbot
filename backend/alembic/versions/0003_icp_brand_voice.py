"""Add brand_voice_id to icp_profiles.

Brand voice profiles (config/brand_voices/*.yaml) live as files, not rows --
that's the point, so a marketer can add one without a migration. This column
just remembers which file name an ICP picked. Nullable, no foreign key,
no backfill: every existing ICP keeps writing in the product's default
voice until someone opens it and picks one.

Revision ID: 0003
Revises: 0002
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("icp_profiles", schema=None) as batch_op:
        batch_op.add_column(sa.Column("brand_voice_id", sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("icp_profiles", schema=None) as batch_op:
        batch_op.drop_column("brand_voice_id")

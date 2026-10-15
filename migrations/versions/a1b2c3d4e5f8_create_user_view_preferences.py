"""Create user_view_preferences table

Revision ID: a1b2c3d4e5f8
Revises: 4124f5b6e6a4
Create Date: 2026-08-31 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

from app.models.constants import INVENTORY_SCHEMA

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f8"
down_revision = "4124f5b6e6a4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_view_preferences",
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("default_view_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "updated_on",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("org_id", "user_id"),
        sa.ForeignKeyConstraint(
            ["default_view_id"],
            [f"{INVENTORY_SCHEMA}.inventory_views.id"],
            ondelete="CASCADE",
        ),
        schema=INVENTORY_SCHEMA,
    )

    op.create_index(
        "idx_uvp_default_view_id",
        "user_view_preferences",
        ["default_view_id"],
        schema=INVENTORY_SCHEMA,
    )


def downgrade():
    op.drop_index("idx_uvp_default_view_id", table_name="user_view_preferences", schema=INVENTORY_SCHEMA)
    op.drop_table("user_view_preferences", schema=INVENTORY_SCHEMA)

"""Create inventory_views table

Revision ID: d4f7a2b8c1e3
Revises: 41e07d4c1092
Create Date: 2026-05-04 10:30:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "d4f7a2b8c1e3"
down_revision = "41e07d4c1092"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "inventory_views",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_system_view",
            sa.Boolean(),
            sa.Computed("org_id IS NULL"),
            nullable=False,
        ),
        sa.Column("configuration", JSONB(), nullable=False),
        sa.Column("org_wide", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema="hbi",
    )

    op.create_index("idx_inventory_views_org_id", "inventory_views", ["org_id"], schema="hbi")
    op.create_index("idx_inventory_views_is_system_view", "inventory_views", ["is_system_view"], schema="hbi")
    op.create_index("idx_inventory_views_created_by", "inventory_views", ["created_by"], schema="hbi")


def downgrade():
    op.drop_index("idx_inventory_views_created_by", table_name="inventory_views", schema="hbi")
    op.drop_index("idx_inventory_views_is_system_view", table_name="inventory_views", schema="hbi")
    op.drop_index("idx_inventory_views_org_id", table_name="inventory_views", schema="hbi")
    op.drop_table("inventory_views", schema="hbi")

"""Add ungrouped_workspaces table and new columns

Revision ID: 286343296975
Revises: 4f0b36e6cf28
Create Date: 2025-02-13 18:58:25.274623

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "286343296975"
down_revision = "4f0b36e6cf28"
branch_labels = None
depends_on = None


def upgrade():
    # Add workspace columns to hosts table
    op.add_column("hosts", sa.Column("workspace_id", sa.UUID(as_uuid=True), nullable=True), schema="hbi")
    op.add_column("hosts", sa.Column("workspace_name", sa.String(length=255), nullable=True), schema="hbi")

    # Add ungrouped_workspaces table
    op.create_table(
        "ungrouped_workspaces",
        sa.Column("id", sa.UUID(as_uuid=True), unique=True, primary_key=True),
        sa.Column("org_id", sa.String(length=36), unique=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="hbi",
    )

    # Add indexes for new columns
    op.create_index("idxworkspaceid", "hosts", ["workspace_id"], if_not_exists=True, schema="hbi")
    op.create_index("idxworkspacename", "hosts", ["workspace_name"], if_not_exists=True, schema="hbi")
    op.create_index("idxuworgid", "ungrouped_workspaces", ["org_id"], if_not_exists=True, schema="hbi")
    op.create_index("idxuwname", "ungrouped_workspaces", ["name"], if_not_exists=True, schema="hbi")


def downgrade():
    # Drop new indexes
    op.drop_index("idxworkspaceid", table_name="hosts", if_exists=True, schema="hbi")
    op.drop_index("idxworkspacename", table_name="hosts", if_exists=True, schema="hbi")
    op.drop_index("idxuworgid", table_name="ungrouped_workspaces", if_exists=True, schema="hbi")
    op.drop_index("idxuwname", table_name="ungrouped_workspaces", if_exists=True, schema="hbi")

    # Drop new table
    op.drop_table("ungrouped_workspaces", schema="hbi")

    # Drop new columns
    op.drop_column("hosts", "workspace_id", schema="hbi")
    op.drop_column("hosts", "workspace_name", schema="hbi")

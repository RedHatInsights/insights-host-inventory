"""Revert previous; add ungrouped column

Revision ID: 25d6dc0e1235
Revises: 286343296975
Create Date: 2025-02-24 09:44:41.232003

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "25d6dc0e1235"
down_revision = "286343296975"
branch_labels = None
depends_on = None


def upgrade():
    # Revert changes from 286343296975
    op.drop_index("idxworkspaceid", table_name="hosts", if_exists=True, schema="hbi")
    op.drop_index("idxworkspacename", table_name="hosts", if_exists=True, schema="hbi")
    op.drop_index("idxuworgid", table_name="ungrouped_workspaces", if_exists=True, schema="hbi")
    op.drop_index("idxuwname", table_name="ungrouped_workspaces", if_exists=True, schema="hbi")

    op.drop_table("ungrouped_workspaces", schema="hbi")

    op.drop_column("hosts", "workspace_id", schema="hbi")
    op.drop_column("hosts", "workspace_name", schema="hbi")

    # Add "ungrouped" boolean column to Groups table
    op.add_column("groups", sa.Column("ungrouped", sa.Boolean, default=False), schema="hbi")
    op.create_index("idxorgidungrouped", "groups", ["org_id", "ungrouped"], if_not_exists=True, schema="hbi")


def downgrade():
    # Drop index & column
    op.drop_index("idxorgidungrouped", table_name="groups", if_exists=True, schema="hbi")
    op.drop_column("groups", "ungrouped", schema="hbi")

    # The rest is just revision 286343296975 again
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

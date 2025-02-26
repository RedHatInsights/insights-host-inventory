"""Remove assignment_rules table

Revision ID: ecbe7e63f6d9
Revises: 25d6dc0e1235
Create Date: 2025-02-25 11:23:48.646278

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "ecbe7e63f6d9"
down_revision = "25d6dc0e1235"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index("idxassrulesorgid", table_name="assignment_rules", if_exists=True, schema="hbi")
    op.drop_table("assignment_rules", schema="hbi")


def downgrade():
    op.create_table(
        "assignment_rules",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("account", sa.String(length=10), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=255)),
        sa.Column("group_id", postgresql.UUID(), sa.ForeignKey("groups.id"), primary_key=True),
        sa.Column(
            "filter", postgresql.JSONB(astext_type=sa.Text()), nullable=False, default=dict, server_default="{}"
        ),
        sa.Column("enabled", sa.Boolean, default=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("modified_on", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "name"),
        schema="hbi",
    )

    op.create_index("idxassrulesorgid", "assignment_rules", ["org_id"], schema="hbi")

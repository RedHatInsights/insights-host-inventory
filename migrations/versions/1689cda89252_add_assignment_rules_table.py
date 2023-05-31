"""Add assignment_rules table

Revision ID: 1689cda89252
Revises: b48ad9e4c8c5
Create Date: 2023-05-30 18:06:39.983078

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "1689cda89252"
down_revision = "b48ad9e4c8c5"
branch_labels = None
depends_on = None


def upgrade():
    # Create the "assignment_rules" table
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
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "name"),
    )

    op.create_index("idxassrulesorgid", "assignment_rules", ["org_id"])


def downgrade():
    op.drop_index("idxassrulesorgid", table_name="assignment_rules")
    op.drop_table("assignment_rules")

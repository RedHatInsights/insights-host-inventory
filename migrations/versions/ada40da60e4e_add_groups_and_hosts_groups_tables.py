"""Add groups and hosts_groups tables

Revision ID: ada40da60e4e
Revises: 69c96c8b47e0
Create Date: 2022-11-30 09:44:32.825899

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "ada40da60e4e"
down_revision = "69c96c8b47e0"
branch_labels = None
depends_on = None


def upgrade():
    # Create the "groups" table
    op.create_table(
        "groups",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("account", sa.String(length=10), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("modified_on", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "name"),
    )

    op.create_index("idxgrouporgid", "groups", ["org_id"])

    # Create the hosts_groups association table
    op.create_table(
        "hosts_groups",
        sa.Column("group_id", postgresql.UUID(), sa.ForeignKey("groups.id"), primary_key=True),
        sa.Column("host_id", postgresql.UUID(), sa.ForeignKey("hosts.id"), primary_key=True),
    )

    op.create_index("idxhostsgroups", "hosts_groups", ["host_id", "group_id"], unique=True)
    op.create_index("idxgroupshosts", "hosts_groups", ["group_id", "host_id"], unique=True)


def downgrade():
    op.drop_index("idxgroupshosts", table_name="hosts_groups")
    op.drop_index("idxhostsgroups", table_name="hosts_groups")
    op.drop_table("hosts_groups")

    op.drop_index("idxgrouporgid", table_name="groups")
    op.drop_table("groups")

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
    op.create_table(
        "groups",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("account", sa.String(length=10), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("created_on", sa.DateTime(), nullable=True),
        sa.Column("modified_on", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("idxgrouporgid", "groups", ["org_id"])

    op.create_table(
        "hosts_groups",
        sa.Column("group_id", postgresql.UUID(), sa.ForeignKey("groups.id"), nullable=False),
        sa.Column("host_id", postgresql.UUID(), sa.ForeignKey("hosts.id"), nullable=False),
        sa.PrimaryKeyConstraint("group_id", "host_id", name="hosts_groups_pk"),
    )

    op.create_index("idxhostsgroups", "hosts_groups", ["host_id", "group_id"], unique=True)
    op.create_index("idxgroupshosts", "hosts_groups", ["group_id", "host_id"], unique=True)


def downgrade():
    op.drop_index("idxgroupshosts", table_name="hosts_groups")
    op.drop_index("idxhostsgroups", table_name="hosts_groups")
    op.drop_table("hosts_groups")

    op.drop_index("idxgrouporgid", table_name="groups")
    op.drop_table("groups")

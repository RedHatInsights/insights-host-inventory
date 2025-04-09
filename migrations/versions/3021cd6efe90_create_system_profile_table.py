"""Create system profile table

Revision ID: 3021cd6efe90
Revises: dbbecd6bf7d1
Create Date: 2024-11-04 15:48:12.022468

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "3021cd6efe90"
down_revision = "dbbecd6bf7d1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("hosts", sa.Column("system_profile_id", postgresql.UUID()))
    op.create_unique_constraint(
        constraint_name="unique_system_profile_id", table_name="hosts", columns=["system_profile_id"]
    )  # 1:1 relationship

    op.create_table(
        "system_profile",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(length=36),
        ),
        sa.Column("os_release", sa.String(length=100)),
        sa.Column("infrastructure_type", sa.String(length=100)),
        sa.Column("infrastructure_vendor", sa.String(length=100)),
        sa.Column("network_interface_id", postgresql.UUID()),
        sa.Column("disk_device_id", postgresql.UUID()),
    )

    op.create_foreign_key(
        "fk_host_system_profile",
        "hosts",
        "system_profile",
        ["system_profile_id"],
        ["id"],
    )

    op.create_table(
        "network_interface",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("ipv4_addresses", sa.ARRAY(sa.String())),
        sa.Column("ipv6_addresses", sa.ARRAY(sa.String())),
        sa.Column("mtu", sa.Integer()),
        sa.Column("mac_address", sa.String()),
        sa.Column("name", sa.String()),
        sa.Column("state", sa.String()),
        sa.Column("type", sa.String()),
    )

    op.create_table(
        "disk_device",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("device", sa.String()),
        sa.Column("label", sa.String()),
        sa.Column("mount_point", sa.String()),
        sa.Column("type", sa.String()),
    )

    op.create_foreign_key(
        "fk_system_profile_network_interface", "system_profile", "network_interface", ["network_interface_id"], ["id"]
    )

    op.create_foreign_key("fk_system_profile_disk_device", "system_profile", "disk_device", ["disk_device_id"], ["id"])


def downgrade():
    op.drop_constraint("fk_host_system_profile", "hosts")

    op.drop_column("hosts", "system_profile_id")

    op.drop_table("system_profile")

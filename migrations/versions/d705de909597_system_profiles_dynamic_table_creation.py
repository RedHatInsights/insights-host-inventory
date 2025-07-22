"""system_profiles_dynamic table creation

Revision ID: d705de909597
Revises: 30b45455a1d2
Create Date: 2025-07-21 20:46:58.570671

"""

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import text

from app.models.constants import INVENTORY_SCHEMA

SP_DYNAMIC_TABLE_NAME = "system_profiles_dynamic"

# revision identifiers, used by Alembic.
revision = "d705de909597"
down_revision = "30b45455a1d2"
branch_labels = None
depends_on = None


def validate_inputs(num_partitions: int):
    """Validate input parameters"""
    if not 1 <= num_partitions <= 32:
        raise ValueError(f"Invalid number of partitions: {num_partitions}. Must be between 1 and 32.")


def upgrade():
    """
    Creates the system_profiles_dynamic table based on the design document.

    This table contains the frequently updated fields from the original system_profile
    to mitigate write amplification. It is partitioned by HASH(org_id)
    to enable partition pruning for multi-tenant performance[cite: 53, 55].
    """

    num_partitions = int(os.getenv("SP_TABLES_NUM_PARTITIONS", 1))
    validate_inputs(num_partitions)
    op.create_table(
        SP_DYNAMIC_TABLE_NAME,
        # --- KEY COLUMNS ---
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("host_id", sa.UUID(as_uuid=True), nullable=False),
        # --- DYNAMIC FIELDS ---
        sa.Column("captured_date", sa.DateTime(timezone=True)),
        sa.Column("running_processes", sa.ARRAY(sa.String), nullable=True),
        sa.Column("last_boot_time", sa.DateTime(timezone=True)),
        sa.Column("installed_packages", sa.ARRAY(sa.String), nullable=True),
        sa.Column("network_interfaces", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("installed_products", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("cpu_flags", sa.ARRAY(sa.String), nullable=True),
        sa.Column("insights_egg_version", sa.String(50), nullable=True),
        sa.Column("kernel_modules", sa.ARRAY(sa.String), nullable=True),
        sa.Column("system_memory_bytes", sa.BigInteger, nullable=True),
        sa.Column("systemd", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # --- CONSTRAINTS ---
        sa.ForeignKeyConstraint(
            ["org_id", "host_id"],
            [f"{INVENTORY_SCHEMA}.hosts.org_id", f"{INVENTORY_SCHEMA}.hosts.id"],
            name=op.f("fk_system_profiles_dynamic_hosts"),
        ),
        sa.PrimaryKeyConstraint("org_id", "host_id", name=op.f("pk_system_profiles_dynamic")),
        schema="hbi",
        postgresql_partition_by="HASH (org_id)",
    )

    # --- PARTITION CREATION ---
    # Create the 32 child partitions to match the vCPU count of the DB instance.
    for i in range(num_partitions):
        op.execute(
            text(f"""
                CREATE TABLE {INVENTORY_SCHEMA}.{SP_DYNAMIC_TABLE_NAME}_p{i}
                PARTITION OF {INVENTORY_SCHEMA}.{SP_DYNAMIC_TABLE_NAME}
                FOR VALUES WITH (MODULUS {num_partitions}, REMAINDER {i});
            """)
        )


def downgrade():
    """
    Removes the system_profiles_dynamic table and its partitions.
    """
    op.drop_table("system_profiles_dynamic", schema="hbi")

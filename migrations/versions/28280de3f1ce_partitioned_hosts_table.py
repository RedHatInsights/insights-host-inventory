"""Partitioned Hosts table

Revision ID: 28280de3f1ce
Revises: 002843d515cb
Create Date: 2025-06-24 14:47:35.196222

"""

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import text

# revision identifiers, used by Alembic.
revision = "28280de3f1ce"
down_revision = "002843d515cb"
branch_labels = None
depends_on = None

INVENTORY_SCHEMA = "hbi"
NUM_PARTITIONS = int(os.getenv("HOSTS_TABLE_NUM_PARTITIONS", 1))
TABLE_NAME = "hosts_new"


def validate_inputs():
    """Validate input parameters"""
    if not 1 <= NUM_PARTITIONS <= 32:
        raise ValueError(f"Invalid number of partitions: {NUM_PARTITIONS}. Must be between 1 and 32.")


def upgrade():
    validate_inputs()

    """
    Creates a new hash-partitioned 'hosts_new' table.
    """
    op.create_table(
        TABLE_NAME,
        # --- Columns ---
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account", sa.String(length=10), nullable=True),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("ansible_host", sa.String(length=255), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=True),
        sa.Column("modified_on", sa.DateTime(timezone=True), nullable=True),
        sa.Column("facts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("tags_alt", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("system_profile_facts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("groups", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("last_check_in", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stale_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deletion_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stale_warning_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reporter", sa.String(length=255), nullable=False),
        sa.Column("per_reporter_staleness", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("canonical_facts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("canonical_facts_version", sa.Integer(), nullable=True),
        sa.Column("is_virtual", sa.Boolean(), nullable=True),
        sa.Column(
            "insights_id",
            sa.UUID(as_uuid=False),
            nullable=False,
            server_default="00000000-0000-0000-0000-000000000000",
        ),
        sa.Column("subscription_manager_id", sa.String(length=36), nullable=True),
        sa.Column("satellite_id", sa.String(length=255), nullable=True),
        sa.Column("fqdn", sa.String(length=255), nullable=True),
        sa.Column("bios_uuid", sa.String(length=36), nullable=True),
        sa.Column("ip_addresses", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("mac_addresses", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("provider_id", sa.String(length=500), nullable=True),
        sa.Column("provider_type", sa.String(length=50), nullable=True),
        # --- Constraints and Indexes ---
        sa.PrimaryKeyConstraint("org_id", "id", name=f"{TABLE_NAME}_pkey"),
        # Table-level Keyword Arguments
        schema=INVENTORY_SCHEMA,
        postgresql_partition_by="HASH (org_id)",
    )

    # Manually create the child partitions.
    # Raw SQL is necessary here as Alembic doesn't have a high-level
    # abstraction for creating partitions of an existing table.
    for i in range(NUM_PARTITIONS):
        partition_name = (
            f"hosts_p{i}"  # Keep the hosts_p{number} pattern to avoid having to rename it after the table switch
        )
        op.execute(
            text(f"""
                CREATE TABLE {INVENTORY_SCHEMA}.{partition_name}
                PARTITION OF {INVENTORY_SCHEMA}.{TABLE_NAME}
                FOR VALUES WITH (MODULUS {NUM_PARTITIONS}, REMAINDER {i});
            """)
        )

    # Basic column indexes
    op.create_index(
        "idx_hosts_modified_on_id",
        TABLE_NAME,
        ["modified_on", "id"],
        schema=INVENTORY_SCHEMA,
        postgresql_ops={"modified_on": "DESC", "id": "DESC"},
    )
    op.create_index("idx_hosts_insights_id", TABLE_NAME, ["insights_id"], unique=False, schema=INVENTORY_SCHEMA)
    op.create_index(
        "idx_hosts_subscription_manager_id",
        TABLE_NAME,
        ["subscription_manager_id"],
        unique=False,
        schema=INVENTORY_SCHEMA,
    )

    # GIN indexes for JSONB columns
    op.create_index(
        "idx_hosts_canonical_facts_gin",
        TABLE_NAME,
        ["canonical_facts"],
        schema=INVENTORY_SCHEMA,
        postgresql_using="gin",
        postgresql_ops={"canonical_facts": "jsonb_path_ops"},
    )
    op.create_index("idx_hosts_groups_gin", TABLE_NAME, ["groups"], schema=INVENTORY_SCHEMA, postgresql_using="gin")

    # Functional indexes
    op.create_index(
        "idx_hosts_host_type", TABLE_NAME, [text("(system_profile_facts ->> 'host_type')")], schema=INVENTORY_SCHEMA
    )
    op.create_index(
        "idx_hosts_cf_insights_id", TABLE_NAME, [text("(canonical_facts ->> 'insights_id')")], schema=INVENTORY_SCHEMA
    )
    op.create_index(
        "idx_hosts_cf_subscription_manager_id",
        TABLE_NAME,
        [text("(canonical_facts ->> 'subscription_manager_id')")],
        schema=INVENTORY_SCHEMA,
    )
    op.create_index(
        "idx_hosts_mssql", TABLE_NAME, [text("(system_profile_facts ->> 'mssql')")], schema=INVENTORY_SCHEMA
    )
    op.create_index(
        "idx_hosts_ansible", TABLE_NAME, [text("(system_profile_facts ->> 'ansible')")], schema=INVENTORY_SCHEMA
    )
    op.create_index(
        "idx_hosts_sap_system",
        TABLE_NAME,
        [text("((system_profile_facts ->> 'sap_system')::boolean)")],
        schema=INVENTORY_SCHEMA,
    )

    # Composite index for common query pattern
    op.create_index(
        "idx_hosts_host_type_modified_on_org_id",
        TABLE_NAME,
        ["org_id", "modified_on", text("(system_profile_facts ->> 'host_type')")],
        schema=INVENTORY_SCHEMA,
    )

    # Indexes with a WHERE clause
    op.create_index(
        "idx_hosts_bootc_status",
        TABLE_NAME,
        ["org_id"],
        schema=INVENTORY_SCHEMA,
        postgresql_where=text("((system_profile_facts -> 'bootc_status' -> 'booted' ->> 'image_digest') IS NOT NULL)"),
    )
    op.create_index(
        "idx_hosts_operating_system_multi",
        TABLE_NAME,
        [
            text("((system_profile_facts -> 'operating_system' ->> 'name'))"),
            text("((system_profile_facts -> 'operating_system' ->> 'major')::integer)"),
            text("((system_profile_facts -> 'operating_system' ->> 'minor')::integer)"),
            text("(system_profile_facts ->> 'host_type')"),
            "modified_on",
            "org_id",
        ],
        schema=INVENTORY_SCHEMA,
        postgresql_where=text("(system_profile_facts -> 'operating_system') IS NOT NULL"),
    )


def downgrade():
    """
    PostgreSQL automatically drops child partitions when the parent table is dropped,
    so there is no need to drop them individually.
    """
    op.drop_table(TABLE_NAME, schema=INVENTORY_SCHEMA)

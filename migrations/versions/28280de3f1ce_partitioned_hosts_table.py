"""Partitioned Hosts and Host Groups tables

Revision ID: 28280de3f1ce
Revises: 002843d515cb
Create Date: 2025-06-24 14:47:35.196222

"""

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import text

from app.models.constants import INVENTORY_SCHEMA

# revision identifiers, used by Alembic.
revision = "28280de3f1ce"
down_revision = "002843d515cb"
branch_labels = None
depends_on = None

HOSTS_TABLE_NAME = "hosts_new"
HOSTS_GROUPS_TABLE_NAME = "hosts_groups_new"


def validate_inputs(num_partitions: int):
    """Validate input parameters"""
    if not 1 <= num_partitions <= 32:
        raise ValueError(f"Invalid number of partitions: {num_partitions}. Must be between 1 and 32.")


def upgrade():
    """
    Creates new hash-partitioned 'hosts_new' and 'hosts_groups_new' tables.
    """

    num_partitions = int(os.getenv("HOSTS_TABLE_NUM_PARTITIONS", 1))
    validate_inputs(num_partitions)

    # ====================================================================
    #  Create hosts_new table
    # ====================================================================
    op.create_table(
        HOSTS_TABLE_NAME,
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
        # --- Constraints ---
        sa.PrimaryKeyConstraint("org_id", "id", name=f"{HOSTS_TABLE_NAME}_pkey"),
        # --- Table Arguments ---
        schema=INVENTORY_SCHEMA,
        postgresql_partition_by="HASH (org_id)",
    )

    # ====================================================================
    #  Create hosts_groups_new table
    # ====================================================================
    op.create_table(
        HOSTS_GROUPS_TABLE_NAME,
        # --- Columns ---
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("host_id", sa.UUID(), nullable=False),
        sa.Column("group_id", sa.UUID(), nullable=False),
        # --- Constraints ---
        sa.PrimaryKeyConstraint("org_id", "host_id", "group_id", name=f"{HOSTS_GROUPS_TABLE_NAME}_pkey"),
        sa.ForeignKeyConstraint(
            ["org_id", "host_id"],
            [f"{INVENTORY_SCHEMA}.{HOSTS_TABLE_NAME}.org_id", f"{INVENTORY_SCHEMA}.{HOSTS_TABLE_NAME}.id"],
            name="fk_hosts_groups_on_hosts",
        ),
        sa.ForeignKeyConstraint(["group_id"], [f"{INVENTORY_SCHEMA}.groups.id"], name="fk_hosts_groups_on_groups"),
        # --- Table Arguments ---
        schema=INVENTORY_SCHEMA,
        postgresql_partition_by="HASH (org_id)",
    )

    # ====================================================================
    #  Create child partitions for BOTH tables
    # ====================================================================
    for i in range(num_partitions):
        # Create partition for hosts_new
        hosts_partition_name = f"hosts_p{i}"
        op.execute(
            text(f"""
                CREATE TABLE {INVENTORY_SCHEMA}.{hosts_partition_name}
                PARTITION OF {INVENTORY_SCHEMA}.{HOSTS_TABLE_NAME}
                FOR VALUES WITH (MODULUS {num_partitions}, REMAINDER {i});
            """)
        )
        # Create partition for hosts_groups_new
        groups_partition_name = f"hosts_groups_p{i}"
        op.execute(
            text(f"""
                CREATE TABLE {INVENTORY_SCHEMA}.{groups_partition_name}
                PARTITION OF {INVENTORY_SCHEMA}.{HOSTS_GROUPS_TABLE_NAME}
                FOR VALUES WITH (MODULUS {num_partitions}, REMAINDER {i});
            """)
        )

    # ====================================================================
    #  Create Indexes for hosts_new
    # ====================================================================
    op.create_index(
        "idx_hosts_modified_on_id",
        HOSTS_TABLE_NAME,
        ["modified_on", "id"],
        schema=INVENTORY_SCHEMA,
        postgresql_ops={"modified_on": "DESC", "id": "DESC"},
    )
    op.create_index("idx_hosts_insights_id", HOSTS_TABLE_NAME, ["insights_id"], unique=False, schema=INVENTORY_SCHEMA)
    op.create_index(
        "idx_hosts_subscription_manager_id",
        HOSTS_TABLE_NAME,
        ["subscription_manager_id"],
        unique=False,
        schema=INVENTORY_SCHEMA,
    )

    op.create_index(
        "idx_hosts_canonical_facts_gin",
        HOSTS_TABLE_NAME,
        ["canonical_facts"],
        schema=INVENTORY_SCHEMA,
        postgresql_using="gin",
        postgresql_ops={"canonical_facts": "jsonb_path_ops"},
    )
    op.create_index(
        "idx_hosts_groups_gin", HOSTS_TABLE_NAME, ["groups"], schema=INVENTORY_SCHEMA, postgresql_using="gin"
    )

    op.create_index(
        "idx_hosts_host_type",
        HOSTS_TABLE_NAME,
        [text("(system_profile_facts ->> 'host_type')")],
        schema=INVENTORY_SCHEMA,
    )
    op.create_index(
        "idx_hosts_cf_insights_id",
        HOSTS_TABLE_NAME,
        [text("(canonical_facts ->> 'insights_id')")],
        schema=INVENTORY_SCHEMA,
    )
    op.create_index(
        "idx_hosts_cf_subscription_manager_id",
        HOSTS_TABLE_NAME,
        [text("(canonical_facts ->> 'subscription_manager_id')")],
        schema=INVENTORY_SCHEMA,
    )
    op.create_index(
        "idx_hosts_mssql", HOSTS_TABLE_NAME, [text("(system_profile_facts ->> 'mssql')")], schema=INVENTORY_SCHEMA
    )
    op.create_index(
        "idx_hosts_ansible", HOSTS_TABLE_NAME, [text("(system_profile_facts ->> 'ansible')")], schema=INVENTORY_SCHEMA
    )
    op.create_index(
        "idx_hosts_sap_system",
        HOSTS_TABLE_NAME,
        [text("((system_profile_facts ->> 'sap_system')::boolean)")],
        schema=INVENTORY_SCHEMA,
    )

    op.create_index(
        "idx_hosts_host_type_modified_on_org_id",
        HOSTS_TABLE_NAME,
        ["org_id", "modified_on", text("(system_profile_facts ->> 'host_type')")],
        schema=INVENTORY_SCHEMA,
    )

    op.create_index(
        "idx_hosts_bootc_status",
        HOSTS_TABLE_NAME,
        ["org_id"],
        schema=INVENTORY_SCHEMA,
        postgresql_where=text("((system_profile_facts -> 'bootc_status' -> 'booted' ->> 'image_digest') IS NOT NULL)"),
    )
    op.create_index(
        "idx_hosts_operating_system_multi",
        HOSTS_TABLE_NAME,
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

    # ====================================================================
    #  Create Indexes for hosts_groups_new
    # ====================================================================
    op.create_index(
        "idx_hosts_groups_forward",
        HOSTS_GROUPS_TABLE_NAME,
        ["org_id", "host_id", "group_id"],
        unique=False,
        schema=INVENTORY_SCHEMA,
    )
    op.create_index(
        "idx_hosts_groups_reverse",
        HOSTS_GROUPS_TABLE_NAME,
        ["org_id", "group_id", "host_id"],
        unique=False,
        schema=INVENTORY_SCHEMA,
    )


def downgrade():
    """
    Drops the new tables. The child partitions are dropped automatically with the parent.
    """
    op.drop_table(HOSTS_GROUPS_TABLE_NAME, schema=INVENTORY_SCHEMA)
    op.drop_table(HOSTS_TABLE_NAME, schema=INVENTORY_SCHEMA)

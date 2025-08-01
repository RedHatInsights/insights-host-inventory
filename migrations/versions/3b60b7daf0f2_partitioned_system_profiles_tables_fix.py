"""Partitioned System Profile tables - Fix

Revision ID: 3b60b7daf0f2
Revises: d705de909597
Create Date: 2025-08-01 08:50:29.997499

"""

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

from app.models.constants import INVENTORY_SCHEMA

# revision identifiers, used by Alembic.
revision = "3b60b7daf0f2"
down_revision = "d705de909597"
branch_labels = None
depends_on = None

SP_DYNAMIC_TABLE_NAME = "system_profiles_dynamic"
SP_STATIC_TABLE_NAME = "system_profiles_static"


def validate_inputs(num_partitions: int):
    """Validate input parameters"""
    if not 1 <= num_partitions <= 32:
        raise ValueError(f"Invalid number of partitions: {num_partitions}. Must be between 1 and 32.")


def upgrade():
    # Get number of partitions from environment variable
    num_partitions = int(os.getenv("HOSTS_TABLES_NUM_PARTITIONS", 1))
    validate_inputs(num_partitions)

    # System profile tables were created using the wrong number of partitions in stage
    # using previous migrations. This block safely drops them only if they are empty
    # before recreating them with the correct number of partitions.
    op.execute(f"""
        DO $$
        BEGIN
            -- Conditionally drop the system_profiles_static table
            IF EXISTS (SELECT FROM pg_tables WHERE schemaname = '{INVENTORY_SCHEMA}'
                AND tablename = '{SP_STATIC_TABLE_NAME}') THEN
                IF NOT EXISTS (SELECT 1 FROM {INVENTORY_SCHEMA}.{SP_STATIC_TABLE_NAME} LIMIT 1) THEN
                    RAISE NOTICE 'Table {SP_STATIC_TABLE_NAME} is empty. Dropping it.';
                    DROP TABLE {INVENTORY_SCHEMA}.{SP_STATIC_TABLE_NAME};
                ELSE
                    RAISE WARNING 'Table {SP_STATIC_TABLE_NAME} is not empty. Skipping drop.';
                END IF;
            END IF;

            -- Conditionally drop the system_profiles_dynamic table
            IF EXISTS (SELECT FROM pg_tables WHERE schemaname = '{INVENTORY_SCHEMA}'
                AND tablename = '{SP_DYNAMIC_TABLE_NAME}') THEN
                IF NOT EXISTS (SELECT 1 FROM {INVENTORY_SCHEMA}.{SP_DYNAMIC_TABLE_NAME} LIMIT 1) THEN
                    RAISE NOTICE 'Table {SP_DYNAMIC_TABLE_NAME} is empty. Dropping it.';
                    DROP TABLE {INVENTORY_SCHEMA}.{SP_DYNAMIC_TABLE_NAME};
                ELSE
                    RAISE WARNING 'Table {SP_DYNAMIC_TABLE_NAME} is not empty. Skipping drop.';
                END IF;
            END IF;
        END;
        $$;
    """)

    op.create_table(
        SP_STATIC_TABLE_NAME,
        # --- PK COLUMNS ---
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("host_id", sa.UUID(as_uuid=True), nullable=False),
        # --- LOGICAL REPLICATION FILTERING COLUMN ---
        sa.Column(
            "insights_id",
            sa.UUID(as_uuid=False),
            nullable=False,
            server_default="00000000-0000-0000-0000-000000000000",
        ),
        # --- STATIC FIELDS ---
        sa.Column("arch", sa.String(length=50), nullable=True),
        sa.Column("basearch", sa.String(length=50), nullable=True),
        sa.Column("bios_release_date", sa.String(length=50), nullable=True),
        sa.Column("bios_vendor", sa.String(length=100), nullable=True),
        sa.Column("bios_version", sa.String(length=100), nullable=True),
        sa.Column("bootc_status", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("cloud_provider", sa.String(length=100), nullable=True),
        sa.Column("conversions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("cores_per_socket", sa.Integer(), nullable=True),
        sa.Column("cpu_model", sa.String(length=100), nullable=True),
        sa.Column("disk_devices", postgresql.ARRAY(postgresql.JSONB()), nullable=True),
        sa.Column("dnf_modules", postgresql.ARRAY(postgresql.JSONB()), nullable=True),
        sa.Column("enabled_services", postgresql.ARRAY(sa.String(length=512)), nullable=True),
        sa.Column("gpg_pubkeys", postgresql.ARRAY(sa.String(length=512)), nullable=True),
        sa.Column("greenboot_fallback_detected", sa.Boolean(), server_default="FALSE", nullable=True),
        sa.Column("greenboot_status", sa.String(length=5), nullable=True),
        sa.Column("host_type", sa.String(length=4), nullable=True),
        sa.Column("image_builder", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("infrastructure_type", sa.String(length=100), nullable=True),
        sa.Column("infrastructure_vendor", sa.String(length=100), nullable=True),
        sa.Column("insights_client_version", sa.String(length=50), nullable=True),
        sa.Column("installed_packages_delta", postgresql.ARRAY(sa.String(length=512)), nullable=True),
        sa.Column("installed_services", postgresql.ARRAY(sa.String(length=512)), nullable=True),
        sa.Column("intersystems", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_marketplace", sa.Boolean(), server_default="FALSE", nullable=True),
        sa.Column("katello_agent_running", sa.Boolean(), server_default="FALSE", nullable=True),
        sa.Column("number_of_cpus", sa.Integer(), nullable=True),
        sa.Column("number_of_sockets", sa.Integer(), nullable=True),
        sa.Column("operating_system", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("os_kernel_version", sa.String(length=20), nullable=True),
        sa.Column("os_release", sa.String(length=100), nullable=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("public_dns", postgresql.ARRAY(sa.String(length=100)), nullable=True),
        sa.Column("public_ipv4_addresses", postgresql.ARRAY(sa.String(length=15)), nullable=True),
        sa.Column("releasever", sa.String(length=100), nullable=True),
        sa.Column("rhc_client_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rhc_config_state", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rhel_ai", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("rhsm", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("rpm_ostree_deployments", postgresql.ARRAY(postgresql.JSONB()), nullable=True),
        sa.Column("satellite_managed", sa.Boolean(), server_default="FALSE", nullable=True),
        sa.Column("selinux_config_file", sa.String(length=128), nullable=True),
        sa.Column("selinux_current_mode", sa.String(length=10), nullable=True),
        sa.Column("subscription_auto_attach", sa.String(length=100), nullable=True),
        sa.Column("subscription_status", sa.String(length=100), nullable=True),
        sa.Column("system_purpose", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("system_update_method", sa.String(length=10), nullable=True),
        sa.Column("third_party_services", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("threads_per_core", sa.Integer(), nullable=True),
        sa.Column("tuned_profile", sa.String(length=256), nullable=True),
        sa.Column("virtual_host_uuid", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("yum_repos", postgresql.ARRAY(postgresql.JSONB()), nullable=True),
        # --- CONSTRAINTS ---
        sa.PrimaryKeyConstraint("org_id", "host_id", name=op.f("pk_system_profiles_static")),
        sa.ForeignKeyConstraint(
            ["org_id", "host_id"],
            [f"{INVENTORY_SCHEMA}.hosts.org_id", f"{INVENTORY_SCHEMA}.hosts.id"],
            name="fk_system_profiles_static_hosts",
        ),
        sa.CheckConstraint(
            "cores_per_socket >= 0 AND cores_per_socket <= 2147483647", name="cores_per_socket_range_check"
        ),
        sa.CheckConstraint("number_of_cpus >= 0 AND number_of_cpus <= 2147483647", name="number_of_cpus_range_check"),
        sa.CheckConstraint(
            "number_of_sockets >= 0 AND number_of_sockets <= 2147483647", name="number_of_sockets_range_check"
        ),
        sa.CheckConstraint(
            "threads_per_core >= 0 AND threads_per_core <= 2147483647", name="threads_per_core_range_check"
        ),
        schema=INVENTORY_SCHEMA,
        postgresql_partition_by="HASH (org_id)",
    )

    # --- PARTITION CREATION ---
    for i in range(num_partitions):
        op.execute(
            text(f"""
                    CREATE TABLE {INVENTORY_SCHEMA}.{SP_STATIC_TABLE_NAME}_p{i}
                    PARTITION OF {INVENTORY_SCHEMA}.{SP_STATIC_TABLE_NAME}
                    FOR VALUES WITH (MODULUS {num_partitions}, REMAINDER {i});
                """)
        )

    # --- INDEX CREATION ---
    op.create_index("idx_system_profiles_static_org_id", SP_STATIC_TABLE_NAME, ["org_id"], schema=INVENTORY_SCHEMA)
    op.create_index("idx_system_profiles_static_host_id", SP_STATIC_TABLE_NAME, ["host_id"], schema=INVENTORY_SCHEMA)
    op.create_index(
        "idx_system_profiles_static_host_type", SP_STATIC_TABLE_NAME, ["host_type"], schema=INVENTORY_SCHEMA
    )
    op.create_index(
        "idx_system_profiles_static_bootc_status", SP_STATIC_TABLE_NAME, ["bootc_status"], schema=INVENTORY_SCHEMA
    )
    op.create_index(
        "idx_system_profiles_static_rhc_client_id", SP_STATIC_TABLE_NAME, ["rhc_client_id"], schema=INVENTORY_SCHEMA
    )
    op.create_index(
        "idx_system_profiles_static_system_update_method",
        SP_STATIC_TABLE_NAME,
        ["system_update_method"],
        schema="hbi",
    )
    op.create_index(
        "idx_system_profiles_static_operating_system_multi",
        SP_STATIC_TABLE_NAME,
        [
            text("((operating_system ->> 'name'))"),
            text("((operating_system ->> 'major')::integer)"),
            text("((operating_system ->> 'minor')::integer)"),
            "org_id",
        ],
        schema=INVENTORY_SCHEMA,
        postgresql_where=text("operating_system IS NOT NULL"),
    )
    op.create_index(
        "idx_system_profiles_static_replica_identity",
        SP_STATIC_TABLE_NAME,
        ["org_id", "host_id", "insights_id"],
        unique=True,
        schema=INVENTORY_SCHEMA,
    )

    # --- REPLICA IDENTITY CREATION ---
    op.execute(
        f"ALTER TABLE {INVENTORY_SCHEMA}.{SP_STATIC_TABLE_NAME} "
        f"REPLICA IDENTITY USING INDEX idx_system_profiles_static_replica_identity;"
    )

    # SYSTEM PROFILE DYNAMIC TABLE CREATION ---
    op.create_table(
        SP_DYNAMIC_TABLE_NAME,
        # --- KEY COLUMNS ---
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("host_id", sa.UUID(as_uuid=True), nullable=False),
        # --- LOGICAL REPLICATION FILTERING COLUMN ---
        sa.Column(
            "insights_id",
            sa.UUID(as_uuid=False),
            nullable=False,
            server_default="00000000-0000-0000-0000-000000000000",
        ),
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
        sa.Column("workloads", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
    for i in range(num_partitions):
        op.execute(
            text(f"""
                    CREATE TABLE {INVENTORY_SCHEMA}.{SP_DYNAMIC_TABLE_NAME}_p{i}
                    PARTITION OF {INVENTORY_SCHEMA}.{SP_DYNAMIC_TABLE_NAME}
                    FOR VALUES WITH (MODULUS {num_partitions}, REMAINDER {i});
                """)
        )

    # --- INDEX CREATION ---
    op.create_index(
        "idx_system_profiles_dynamic_workloads_gin",
        SP_DYNAMIC_TABLE_NAME,
        ["workloads"],
        schema=INVENTORY_SCHEMA,
        postgresql_using="gin",
    )
    op.create_index(
        "idx_system_profiles_dynamic_replica_identity",
        SP_DYNAMIC_TABLE_NAME,
        ["org_id", "host_id", "insights_id"],
        unique=True,
        schema=INVENTORY_SCHEMA,
    )

    op.execute(
        f"ALTER TABLE {INVENTORY_SCHEMA}.{SP_DYNAMIC_TABLE_NAME} "
        f"REPLICA IDENTITY USING INDEX idx_system_profiles_dynamic_replica_identity;"
    )

    # --- CREATE TRIGGER TO SYNC insights_id ---
    op.execute(f"""
        CREATE OR REPLACE FUNCTION {INVENTORY_SCHEMA}.sync_insights_id_to_profiles()
        RETURNS TRIGGER AS $$
        BEGIN
            IF (TG_OP = 'INSERT'
                OR (TG_OP = 'UPDATE' AND NEW.insights_id IS DISTINCT FROM OLD.insights_id)) THEN
                -- Update the corresponding row in the dynamic profile table.
                UPDATE {INVENTORY_SCHEMA}.{SP_DYNAMIC_TABLE_NAME}
                SET insights_id = NEW.insights_id
                WHERE host_id = NEW.id AND org_id = NEW.org_id;

                -- Update the corresponding row in the static profile table.
                UPDATE {INVENTORY_SCHEMA}.{SP_STATIC_TABLE_NAME}
                SET insights_id = NEW.insights_id
                WHERE host_id = NEW.id AND org_id = NEW.org_id;
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # The WHEN clause is removed, and the logic is moved into the function.
    op.execute(f"""
        CREATE TRIGGER trigger_sync_insights_id
        AFTER INSERT OR UPDATE OF insights_id ON {INVENTORY_SCHEMA}.hosts
        FOR EACH ROW
        EXECUTE FUNCTION {INVENTORY_SCHEMA}.sync_insights_id_to_profiles();
    """)


def downgrade():
    """
    Removes the system_profiles_static and system_profiles_dynamic tables
    and their partitions, as well as the synchronization trigger.
    """
    op.execute(f"DROP TRIGGER IF EXISTS trigger_sync_insights_id ON {INVENTORY_SCHEMA}.hosts;")
    op.execute(f"DROP FUNCTION IF EXISTS {INVENTORY_SCHEMA}.sync_insights_id_to_profiles();")
    op.drop_table(SP_STATIC_TABLE_NAME, schema=INVENTORY_SCHEMA)
    op.drop_table(SP_DYNAMIC_TABLE_NAME, schema=INVENTORY_SCHEMA)

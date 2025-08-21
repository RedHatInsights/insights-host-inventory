"""Logical Replication - Prerequisites

Revision ID: 6714f3063d90
Revises: 96e12ae08c05
Create Date: 2025-08-06 13:57:13.109100
"""

import os

from alembic import op
from sqlalchemy import text

from app.models.constants import INVENTORY_SCHEMA

# revision identifiers, used by Alembic.
revision = "6714f3063d90"
down_revision = "96e12ae08c05"
branch_labels = None
depends_on = None

SP_DYNAMIC_TABLE_NAME = "system_profiles_dynamic"
SP_STATIC_TABLE_NAME = "system_profiles_static"


"""
This migration prepares the `hosts`, `system_profiles_dynamic`, and `system_profiles_static` tables
for logical replication by:
   1. Creating a unique index on (org_id, id, insights_id) in the `hosts` table and setting it as the replica identity.
      - In "automated" mode: Creates the index directly on the parent table.
      - In "managed" mode: Builds indexes concurrently on each partition first, waits for
        completion, then creates the parent index. (Stage and Prod)
   2. Creating new triggers and functions to keep `insights_id` values in the
      `system_profiles_static` and `system_profiles_dynamic` tables in sync with updates
      to the `hosts` table.

The `insights_id` field in the system profile tables is used solely to filter out records
during logical replication. It is not itself replicated, and the application does not need to know it exists.
"""


def validate_num_partitions(num_partitions: int):
    if not 1 <= num_partitions <= 32:
        raise ValueError(f"Invalid number of partitions: {num_partitions}. Must be between 1 and 32.")


def upgrade():
    migration_mode = os.environ.get("MIGRATION_MODE", "automated").lower()

    if migration_mode == "automated":
        op.create_index(
            "hosts_replica_identity_idx",
            "hosts",
            ["org_id", "id", "insights_id"],
            unique=True,
            schema=INVENTORY_SCHEMA,
        )
        op.execute(f"ALTER TABLE {INVENTORY_SCHEMA}.hosts REPLICA IDENTITY USING INDEX hosts_replica_identity_idx;")

    elif migration_mode == "managed":
        num_partitions = int(os.getenv("HOSTS_TABLE_NUM_PARTITIONS", 1))
        validate_num_partitions(num_partitions)

        # Step 1: Create concurrent indexes on all partitions
        for i in range(num_partitions):
            index_name = f"hosts_p{i}_replica_identity_idx"
            partition_name = f"{INVENTORY_SCHEMA}.hosts_p{i}"

            with op.get_context().autocommit_block():
                op.execute(
                    text(f"""
                        CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS {index_name}
                        ON {partition_name} (org_id, id, insights_id);
                    """)
                )

        # Step 2: Wait for all concurrent index builds to complete before locking parent table
        op.execute(
            text("""
            DO $$
            DECLARE
                idx_builds INT;
            BEGIN
                RAISE NOTICE 'Waiting for all concurrent index builds to complete...';
                LOOP
                    SELECT COUNT(*) INTO idx_builds
                    FROM pg_stat_progress_create_index
                    WHERE command = 'CREATE INDEX' AND phase != 'done';

                    EXIT WHEN idx_builds = 0;

                    RAISE NOTICE 'Still % ongoing index builds... sleeping 10s', idx_builds;
                    PERFORM pg_sleep(10);
                END LOOP;
                RAISE NOTICE 'All concurrent index builds are complete.';
            END;
            $$;
            """)
        )

        # Step 3: Create the parent index (will take a lock briefly)
        op.execute(
            text(f"""
                CREATE UNIQUE INDEX IF NOT EXISTS hosts_replica_identity_idx
                ON {INVENTORY_SCHEMA}.hosts (org_id, id, insights_id);
            """)
        )

        # Step 4: Set replica identity on the parent table
        op.execute(f"ALTER TABLE {INVENTORY_SCHEMA}.hosts REPLICA IDENTITY USING INDEX hosts_replica_identity_idx;")

    # Drop triggers created in previous migrations
    op.execute(f"DROP TRIGGER IF EXISTS trigger_sync_insights_id ON {INVENTORY_SCHEMA}.hosts;")
    op.execute(f"DROP FUNCTION IF EXISTS {INVENTORY_SCHEMA}.sync_insights_id_to_profiles();")

    # Create triggers to sync the insights_id in the new system_profile tables
    op.execute(f"""
        CREATE OR REPLACE FUNCTION {INVENTORY_SCHEMA}.sync_insights_id_to_system_profiles()
        RETURNS TRIGGER AS $$
        BEGIN
            IF (TG_OP = 'UPDATE' AND NEW.insights_id IS DISTINCT FROM OLD.insights_id) THEN
                UPDATE {INVENTORY_SCHEMA}.{SP_STATIC_TABLE_NAME}
                SET insights_id = NEW.insights_id
                WHERE org_id = NEW.org_id AND host_id = NEW.id;

                UPDATE {INVENTORY_SCHEMA}.{SP_DYNAMIC_TABLE_NAME}
                SET insights_id = NEW.insights_id
                WHERE org_id = NEW.org_id AND host_id = NEW.id;
            END IF;

            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute(f"""
        CREATE TRIGGER trigger_sync_insights_id_to_system_profiles
        AFTER UPDATE OF insights_id ON {INVENTORY_SCHEMA}.hosts
        FOR EACH ROW
        EXECUTE FUNCTION {INVENTORY_SCHEMA}.sync_insights_id_to_system_profiles();
    """)

    op.execute(f"""
        CREATE OR REPLACE FUNCTION {INVENTORY_SCHEMA}.populate_system_profiles_static_insights_id()
        RETURNS TRIGGER AS $$
        DECLARE
            v_host_insights_id UUID;
        BEGIN
            SELECT insights_id INTO v_host_insights_id
            FROM {INVENTORY_SCHEMA}.hosts
            WHERE org_id = NEW.org_id AND id = NEW.host_id;

            IF v_host_insights_id IS DISTINCT FROM NEW.insights_id THEN
                UPDATE {INVENTORY_SCHEMA}.{SP_STATIC_TABLE_NAME}
                SET insights_id = v_host_insights_id
                WHERE org_id = NEW.org_id AND host_id = NEW.host_id;
            END IF;

            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute(f"""
        CREATE TRIGGER trigger_populate_system_profiles_static_insights_id
        AFTER INSERT ON {INVENTORY_SCHEMA}.{SP_STATIC_TABLE_NAME}
        FOR EACH ROW
        EXECUTE FUNCTION {INVENTORY_SCHEMA}.populate_system_profiles_static_insights_id();
       """)

    op.execute(f"""
        CREATE OR REPLACE FUNCTION {INVENTORY_SCHEMA}.populate_system_profiles_dynamic_insights_id()
        RETURNS TRIGGER AS $$
        DECLARE
            v_host_insights_id UUID;
        BEGIN
            SELECT insights_id INTO v_host_insights_id
            FROM {INVENTORY_SCHEMA}.hosts
            WHERE org_id = NEW.org_id AND id = NEW.host_id;

            IF v_host_insights_id IS DISTINCT FROM NEW.insights_id THEN
                UPDATE {INVENTORY_SCHEMA}.{SP_DYNAMIC_TABLE_NAME}
                SET insights_id = v_host_insights_id
                WHERE org_id = NEW.org_id AND host_id = NEW.host_id;
            END IF;

            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute(f"""
        CREATE TRIGGER trigger_populate_system_profiles_dynamic_insights_id
        AFTER INSERT ON {INVENTORY_SCHEMA}.{SP_DYNAMIC_TABLE_NAME}
        FOR EACH ROW
        EXECUTE FUNCTION {INVENTORY_SCHEMA}.populate_system_profiles_dynamic_insights_id();
    """)


def downgrade():
    op.execute(f"ALTER TABLE {INVENTORY_SCHEMA}.hosts REPLICA IDENTITY DEFAULT;")

    # Unfortunately there is no way to drop indexes concurrently on partitioned tables
    op.drop_index("hosts_replica_identity_idx", table_name="hosts", schema=INVENTORY_SCHEMA)

    op.execute(f"DROP TRIGGER IF EXISTS trigger_sync_insights_id_to_system_profiles ON {INVENTORY_SCHEMA}.hosts;")
    op.execute(f"DROP FUNCTION IF EXISTS {INVENTORY_SCHEMA}.sync_insights_id_to_system_profiles();")
    op.execute(
        f"DROP TRIGGER IF EXISTS trigger_populate_system_profiles_static_insights_id "
        f"ON {INVENTORY_SCHEMA}.{SP_STATIC_TABLE_NAME};"
    )
    op.execute(f"DROP FUNCTION IF EXISTS {INVENTORY_SCHEMA}.populate_system_profiles_static_insights_id();")
    op.execute(
        f"DROP TRIGGER IF EXISTS trigger_populate_system_profiles_dynamic_insights_id "
        f"ON {INVENTORY_SCHEMA}.{SP_DYNAMIC_TABLE_NAME};"
    )
    op.execute(f"DROP FUNCTION IF EXISTS {INVENTORY_SCHEMA}.populate_system_profiles_dynamic_insights_id();")

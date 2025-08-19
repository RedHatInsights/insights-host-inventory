"""add new workloads index

Revision ID: 6543659c6fe0
Revises: b85583af35ca
Create Date: 2025-09-09 08:11:38.073367

"""

import os

from alembic import op
from sqlalchemy import text

from app.models.constants import INVENTORY_SCHEMA

# revision identifiers, used by Alembic.
revision = "6543659c6fe0"
down_revision = "b85583af35ca"
branch_labels = None
depends_on = None


def validate_num_partitions(num_partitions: int):
    if not 1 <= num_partitions <= 32:
        raise ValueError(f"Invalid number of partitions: {num_partitions}. Must be between 1 and 32.")


def upgrade():
    migration_mode = os.environ.get("MIGRATION_MODE", "automated").lower()

    if migration_mode == "automated":
        op.create_index(
            "idx_hosts_system_profiles_workloads_gin",
            "hosts",
            [text("(system_profile_facts -> 'workloads')")],
            schema=INVENTORY_SCHEMA,
            postgresql_using="gin",
        )
    elif migration_mode == "managed":
        num_partitions = int(os.getenv("HOSTS_TABLE_NUM_PARTITIONS", 1))
        validate_num_partitions(num_partitions)

        # Step 1: Create concurrent indexes on all partitions
        for i in range(num_partitions):
            index_name = f"idx_hosts_p{i}_system_profiles_workloads_gin"
            partition_name = f"{INVENTORY_SCHEMA}.hosts_p{i}"

            with op.get_context().autocommit_block():
                op.execute(
                    text(f"""
                        CREATE INDEX CONCURRENTLY IF NOT EXISTS
                        {index_name} ON {partition_name}
                        USING GIN ((system_profile_facts -> 'workloads'));
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
                CREATE INDEX IF NOT EXISTS idx_hosts_system_profiles_workloads_gin
                ON {INVENTORY_SCHEMA}.hosts USING GIN ((system_profile_facts -> 'workloads'));
            """)
        )


def downgrade():
    migration_mode = os.environ.get("MIGRATION_MODE", "automated").lower()

    if migration_mode == "managed":
        with op.get_context().autocommit_block():
            op.drop_index(
                "idx_hosts_system_profiles_workloads_gin",
                table_name="hosts",
                schema=INVENTORY_SCHEMA,
            )
    elif migration_mode == "automated":
        op.drop_index(
            "idx_hosts_system_profiles_workloads_gin",
            table_name="hosts",
            schema=INVENTORY_SCHEMA,
        )

"""Hosts Table - Logical replication

Revision ID: 6714f3063d90
Revises: 3b60b7daf0f2
Create Date: 2025-08-06 13:57:13.109100
"""

import os

from alembic import op
from sqlalchemy import text

from app.models.constants import INVENTORY_SCHEMA

# revision identifiers, used by Alembic.
revision = "6714f3063d90"
down_revision = "3b60b7daf0f2"
branch_labels = None
depends_on = None


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
                        CREATE UNIQUE INDEX CONCURRENTLY {index_name}
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
                CREATE UNIQUE INDEX hosts_replica_identity_idx
                ON {INVENTORY_SCHEMA}.hosts (org_id, id, insights_id);
            """)
        )

        # Step 4: Set replica identity on the parent table
        op.execute(f"ALTER TABLE {INVENTORY_SCHEMA}.hosts REPLICA IDENTITY USING INDEX hosts_replica_identity_idx;")


def downgrade():
    # Step 1: Reset replica identity
    op.execute(f"ALTER TABLE {INVENTORY_SCHEMA}.hosts REPLICA IDENTITY DEFAULT;")

    # Step 2: Drop the index
    # Unfortunately there is no way to drop indexes concurrently on partitioned tables
    op.drop_index("hosts_replica_identity_idx", table_name="hosts", schema=INVENTORY_SCHEMA)

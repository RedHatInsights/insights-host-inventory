#!/usr/bin/python3
"""
Helper function for creating indexes on partitioned tables.

This module provides a utility function to create indexes on partitioned tables.
It creates indexes on all partitions first using CREATE INDEX CONCURRENTLY,
then creates the index on the parent table using CREATE INDEX.
"""

from alembic import op
from sqlalchemy import text

from app.logging import get_logger
from app.models.constants import INVENTORY_SCHEMA
from migrations.helpers import MIGRATION_MODE
from migrations.helpers import TABLE_NUM_PARTITIONS
from migrations.helpers import validate_num_partitions

logger = get_logger(__name__)


def create_partitioned_table_index(
    table_name: str,
    index_name: str,
    index_definition: str,
    num_partitions: int | None = None,
    schema: str = INVENTORY_SCHEMA,
    unique: bool = False,
) -> None:
    """
    Create an index on a partitioned table and all its partitions.

    This function creates indexes following PostgreSQL best practices for partitioned tables:
    - In "automated" mode: Creates the index directly on the parent table.
    - In "managed" mode: Creates indexes on all partitions first using CREATE INDEX CONCURRENTLY,
      then creates the index on the parent table using CREATE INDEX.

    Args:
        table_name: Name of the parent table (without schema prefix)
        index_name: Name for the index (will be prefixed for partitions)
        index_definition: The column definition for the index (e.g., "(column1, column2)" or "((jsonb_col -> 'key'))")
        num_partitions: Number of partitions (0 to num_partitions-1). Defaults to HOSTS_TABLE_NUM_PARTITIONS env var
        schema: Database schema name. Defaults to INVENTORY_SCHEMA
        unique: Create an UNIQUE index. Defaults to False

    Example:
        create_partitioned_table_index(
            table_name="hosts",
            index_name="idx_hosts_last_check_in",
            index_definition="(last_check_in)",
            num_partitions=32
        )

    Raises:
        ValueError: If num_partitions is not between 1 and 32
        Exception: For any database errors during index creation
    """
    if num_partitions is None:
        num_partitions = TABLE_NUM_PARTITIONS

    validate_num_partitions(num_partitions)

    migration_mode = MIGRATION_MODE

    logger.info(
        f"Creating index '{index_name}' on partitioned table '{schema}.{table_name}' "
        f"with {num_partitions} partitions in '{migration_mode}' mode"
    )

    if migration_mode == "automated":
        # For automated mode (local, ephemeral, on-premise), create index directly on parent table
        logger.info(f"Creating index '{index_name}' directly on parent table '{schema}.{table_name}'")

        unique_clause = "UNIQUE" if unique else ""

        op.execute(
            text(f"""
                CREATE {unique_clause} INDEX IF NOT EXISTS {index_name}
                ON {schema}.{table_name} {index_definition};
            """)
        )

        logger.info(f"Successfully created index '{index_name}' on parent table")

    else:
        # For managed mode (stage, production), create concurrent indexes on partitions first
        try:
            # Step 1: Create indexes on all partition tables using CREATE INDEX CONCURRENTLY
            logger.info(f"Creating indexes on {num_partitions} partitions using CREATE INDEX CONCURRENTLY...")

            unique_clause = "UNIQUE" if unique else ""

            for i in range(num_partitions):
                partition_name = f"{table_name}_p{i}"
                partition_index_name = f"{table_name}_p{i}_{index_name}"

                logger.info(f"  Creating index '{partition_index_name}' on partition '{partition_name}'")

                with op.get_context().autocommit_block():
                    op.execute(
                        text(f"""
                            CREATE {unique_clause} INDEX CONCURRENTLY IF NOT EXISTS {partition_index_name}
                            ON {schema}.{partition_name} {index_definition};
                        """)
                    )

            logger.info("Successfully created indexes on all partitions")

            # Step 2: Wait for all concurrent index builds to complete
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

            # Step 3: Create index on parent table using CREATE INDEX
            logger.info(f"Creating index '{index_name}' on parent table '{schema}.{table_name}'")

            op.execute(
                text(f"""
                    CREATE {unique_clause} INDEX IF NOT EXISTS {index_name}
                    ON {schema}.{table_name} {index_definition};
                """)
            )

            logger.info(f"Successfully created index '{index_name}' on parent table and all partitions")

        except Exception as e:
            logger.error(f"Error creating index '{index_name}' on partitioned table '{schema}.{table_name}': {e}")
            raise


def drop_partitioned_table_index(
    table_name: str,
    index_name: str,
    num_partitions: int | None = None,
    schema: str = INVENTORY_SCHEMA,
    if_exists: bool = True,
) -> None:
    """
    Drop an index from a partitioned table and all its partitions.

    This is a utility function to clean up indexes created by create_partitioned_table_index.
    - In "automated" mode: Drops the index directly from the parent table.
    - In "managed" mode: Drops the parent index first, then all partition indexes.

    Args:
        table_name: Name of the parent table (without schema prefix)
        index_name: Name of the index to drop
        num_partitions: Number of partitions (0 to num_partitions-1). Defaults to HOSTS_TABLE_NUM_PARTITIONS env var
        schema: Database schema name. Defaults to INVENTORY_SCHEMA
        if_exists: Whether to use IF EXISTS clause. Defaults to True

    Raises:
        ValueError: If num_partitions is not between 1 and 32
        Exception: For any database errors during index dropping
    """
    if num_partitions is None:
        num_partitions = TABLE_NUM_PARTITIONS

    validate_num_partitions(num_partitions)

    migration_mode = MIGRATION_MODE

    logger.info(
        f"Dropping index '{index_name}' from partitioned table '{schema}.{table_name}' "
        f"and its {num_partitions} partitions in '{migration_mode}' mode"
    )

    if migration_mode == "automated":
        # For automated mode (local, ephemeral, on-premise), drop index directly from parent table
        logger.info(f"Dropping index '{index_name}' directly from parent table '{schema}.{table_name}'")

        op.drop_index(index_name, table_name=table_name, schema=schema, if_exists=if_exists)

        logger.info(f"Successfully dropped index '{index_name}' from parent table")

    else:
        # For managed mode (stage, production), drop the parent index.
        # PostgreSQL automatically cascades the drop to all partition indexes.
        #
        # Note: DROP INDEX CONCURRENTLY cannot be used on partitioned tables
        # (PostgreSQL limitation), so we must use regular DROP INDEX which
        # acquires ACCESS EXCLUSIVE lock. This is unavoidable for partitioned indexes.
        if_exists_clause = "IF EXISTS" if if_exists else ""

        try:
            logger.info(f"Dropping index '{index_name}' from parent table '{schema}.{table_name}'")
            logger.info("(Partition indexes will be dropped automatically by PostgreSQL)")

            op.execute(
                text(f"""
                    DROP INDEX {if_exists_clause} {schema}.{index_name};
                """)
            )

            logger.info(f"Successfully dropped index '{index_name}' from parent table and all partitions")

        except Exception as e:
            logger.error(f"Error dropping index '{index_name}' from partitioned table '{schema}.{table_name}': {e}")
            raise

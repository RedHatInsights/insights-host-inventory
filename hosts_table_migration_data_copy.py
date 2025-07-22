#!/usr/bin/python
# ruff: noqa: E501
import os
import sys
import time
from functools import partial
from logging import Logger

from connexion import FlaskApp
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.environment import RuntimeEnvironment
from app.logging import get_logger
from app.models.constants import INVENTORY_SCHEMA
from jobs.common import excepthook
from jobs.common import job_setup

PROMETHEUS_JOB = "hosts-table-migration-data-copy"
LOGGER_NAME = "hosts_table_migration_data_copy"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB
SUSPEND_JOB = os.environ.get("SUSPEND_JOB", "true").lower() == "true"
PAGINATION_INDEX_NAME = "idx_hosts_migration_pagination_temp"

"""
This job copies all historical data from the original 'hosts' table into the
new partitioned tables ('hosts_new' and 'hosts_groups_new'). It processes
data in batches to manage memory and WAL size.

This script should only be run during a planned maintenance window.
"""


def create_index(session: Session, logger: Logger):
    # Step 0: Create the index
    index_exists_query = text("""
                              SELECT EXISTS (SELECT 1
                                             FROM pg_indexes
                                             WHERE schemaname = :schema
                                               AND indexname = :index_name);
                              """)
    result = session.execute(index_exists_query, {"schema": INVENTORY_SCHEMA, "index_name": PAGINATION_INDEX_NAME})
    index_exists = result.scalar_one()

    session.commit()

    if not index_exists:
        logger.info("Index does not exist. Creating it now (this may take a long time)...")

        # CREATE INDEX CONCURRENTLY cannot run inside a transaction.
        # We get the raw DBAPI connection and set it to autocommit mode for this operation.
        connection = session.connection().connection
        isolation_level_before = connection.isolation_level
        connection.set_isolation_level(0)  # 0 = autocommit

        try:
            create_index_sql = text(f"""
                CREATE INDEX CONCURRENTLY {PAGINATION_INDEX_NAME}
                ON {INVENTORY_SCHEMA}.hosts (created_on, id);
            """)
            session.execute(create_index_sql)
            logger.info("Successfully created temporary pagination index.")
        finally:
            # Restore the original isolation level to resume normal transactional behavior.
            connection.set_isolation_level(isolation_level_before)
    else:
        logger.info("Temporary pagination index already exists.")


def update_table_column(session: Session, logger: Logger):
    # We get the raw DBAPI connection and set it to autocommit mode for this operation.
    connection = session.connection().connection
    isolation_level_before = connection.isolation_level
    connection.set_isolation_level(0)  # 0 = autocommit

    try:
        update_column = text(f"""ALTER TABLE {INVENTORY_SCHEMA}.hosts_new ALTER COLUMN bios_uuid TYPE VARCHAR(255);""")
        session.execute(update_column)
        logger.info("Successfully updated column")
    finally:
        # Restore the original isolation level to resume normal transactional behavior.
        connection.set_isolation_level(isolation_level_before)


def copy_data_in_batches(session: Session, logger: Logger):
    """
    Copies data from the old hosts table to the new partitioned tables using
    a batched, keyset pagination approach for efficiency.
    """
    batch_size = int(os.getenv("HOSTS_TABLE_MIGRATION_BATCH_SIZE", 5000))
    # Initialize cursor for pagination using a guaranteed sequential column
    last_created_on = "1970-01-01 00:00:00+00"
    last_id = "00000000-0000-0000-0000-000000000000"
    total_rows_copied = 0

    logger.info(f"Starting batched data migration with a batch size of {batch_size} rows.")

    while True:
        batch_start_time = time.perf_counter()

        # Step 1: Fetch the next batch of hosts.
        logger.info(f"Fetching next batch of hosts created after: {last_created_on} - {last_id}")

        # Fetch both id and created_on to determine the next starting point
        batch_to_process = session.execute(
            text(f"""
                SELECT id, created_on FROM {INVENTORY_SCHEMA}.hosts
                WHERE (created_on, id) > (:last_created_on, :last_id)
                ORDER BY created_on, id
                LIMIT :batch_size;
            """),
            {"last_created_on": last_created_on, "last_id": last_id, "batch_size": batch_size},
        ).fetchall()

        if not batch_to_process:
            logger.info("No more hosts to process. Data migration complete.")
            break

        # Extract just the IDs for the WHERE...IN clause, which is very efficient
        id_list = [row[0] for row in batch_to_process]
        logger.info(f"Processing batch of {len(id_list)} hosts...")

        # Step 2: Copy the host data for the current batch
        hosts_insert_sql = f"""
            INSERT INTO {INVENTORY_SCHEMA}.hosts_new (
                org_id, id, account, display_name, ansible_host, created_on, modified_on, facts, tags,
                tags_alt, system_profile_facts, groups, last_check_in, stale_timestamp, deletion_timestamp,
                stale_warning_timestamp, reporter, per_reporter_staleness, canonical_facts,
                canonical_facts_version, is_virtual, insights_id, subscription_manager_id,
                satellite_id, fqdn, bios_uuid, ip_addresses, mac_addresses, provider_id, provider_type
            )
            SELECT
                h.org_id, h.id, h.account, h.display_name, h.ansible_host, h.created_on,
                h.modified_on, h.facts, h.tags, h.tags_alt, h.system_profile_facts,
                h.groups, h.last_check_in, h.stale_timestamp, h.deletion_timestamp,
                h.stale_warning_timestamp, h.reporter, h.per_reporter_staleness,
                h.canonical_facts,
                (h.canonical_facts ->> 'canonical_facts_version')::integer,
                (h.canonical_facts ->> 'is_virtual')::boolean,
                COALESCE((h.canonical_facts->>'insights_id')::uuid, '00000000-0000-0000-0000-000000000000'),
                h.canonical_facts ->> 'subscription_manager_id',
                h.canonical_facts ->> 'satellite_id',
                h.canonical_facts ->> 'fqdn',
                h.canonical_facts ->> 'bios_uuid',
                h.canonical_facts -> 'ip_addresses',
                h.canonical_facts -> 'mac_addresses',
                h.canonical_facts ->> 'provider_id',
                h.canonical_facts ->> 'provider_type'
            FROM {INVENTORY_SCHEMA}.hosts h
            WHERE h.id = ANY(:id_list)
            ON CONFLICT (org_id, id) DO NOTHING;
        """
        session.execute(text(hosts_insert_sql), {"id_list": id_list})

        # Step 3: Copy the host_groups data for the current batch
        hosts_groups_insert_sql = f"""
            INSERT INTO {INVENTORY_SCHEMA}.hosts_groups_new (org_id, host_id, group_id)
            SELECT
                h.org_id,
                h.id,
                (g.value ->> 'id')::uuid
            FROM
                {INVENTORY_SCHEMA}.hosts h,
                jsonb_array_elements(h.groups) AS g(value)
            WHERE
                h.id = ANY(:id_list)
                AND jsonb_typeof(h.groups) = 'array' AND jsonb_array_length(h.groups) > 0
            ON CONFLICT (org_id, host_id, group_id) DO NOTHING;
        """
        session.execute(text(hosts_groups_insert_sql), {"id_list": id_list})

        # Update loop variables with the last row from the processed batch
        last_row = batch_to_process[-1]
        last_created_on = last_row[1]
        last_id = last_row[0]

        total_rows_copied += len(id_list)
        batch_duration = time.perf_counter() - batch_start_time

        logger.info(
            f"Batch complete in {batch_duration:.2f}s. "
            f"Total rows copied so far: {total_rows_copied}. "
            f"Next batch starts after: {last_created_on}"
        )

        session.commit()

    logger.info(f"Successfully finished copying all data. Total rows processed: {total_rows_copied}.")


def run(logger: Logger, session: Session, application: FlaskApp):
    """Main execution function."""
    try:
        with application.app.app_context():
            create_index(session, logger)
            update_table_column(session, logger)
            copy_data_in_batches(session, logger)
    except Exception:
        logger.exception("A critical error occurred during the data copy job.")
        raise
    finally:
        logger.info("Closing database session.")
        session.close()


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)

    if SUSPEND_JOB:
        logger.info("SUSPEND_JOB set to true; exiting.")
        sys.exit(0)

    job_type = "Hosts partitioned tables full data copy"
    sys.excepthook = partial(excepthook, logger, job_type)

    config, session, _, _, _, application = job_setup((), PROMETHEUS_JOB)

    run(logger, session, application)

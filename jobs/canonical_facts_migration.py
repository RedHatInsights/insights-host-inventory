#!/usr/bin/python3
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

PROMETHEUS_JOB = "canonical-facts-migration"
LOGGER_NAME = "canonical_facts_migration"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB
SUSPEND_JOB = os.environ.get("SUSPEND_CANONICAL_FACTS_MIGRATION", "true").lower() == "true"

"""
This job updates the canonical facts columns in the hosts table by extracting
values from the canonical_facts JSONB column. It processes data in batches
to manage memory and avoid long-running transactions.

This script can be run safely on a live system as it only performs UPDATE operations.
"""

# Single Source of Truth for Index DDL
INDEX_DEFINITIONS = {
    "hosts_replica_identity_idx": "CREATE UNIQUE INDEX {index_name} ON {schema}.hosts (org_id, id, insights_id);",
    "idx_hosts_insights_id": "CREATE INDEX {index_name} ON {schema}.hosts (insights_id);",
    "idx_hosts_subscription_manager_id": "CREATE INDEX {index_name} ON {schema}.hosts (subscription_manager_id);",
}


def drop_indexes(session: Session, logger: Logger):
    """Drops all non-primary key indexes from the target tables to speed up inserts."""
    logger.warning("Dropping all non-PK indexes from target tables to optimize data copy...")
    for index_name in INDEX_DEFINITIONS.keys():
        logger.info(f"  Dropping index: {index_name}")
        session.execute(text(f"DROP INDEX IF EXISTS {INVENTORY_SCHEMA}.{index_name};"))
    session.commit()
    logger.info("All non-PK indexes have been dropped.")


def recreate_indexes(session: Session, logger: Logger):
    """Recreates all indexes using a data-driven approach after the data copy is complete."""
    logger.info("Data copy finished. Recreating all indexes (this may take a long time)...")
    try:
        for index_name, index_ddl in INDEX_DEFINITIONS.items():
            logger.info(f"  Recreating index: {index_name}")
            session.execute(text(index_ddl.format(index_name=index_name, schema=INVENTORY_SCHEMA)))

        logger.info("Committing index creation transaction...")
        session.commit()
        logger.info("All indexes have been recreated successfully.")
    except Exception:
        logger.error("An error occurred during index recreation. Rolling back.")
        session.rollback()
        raise


def update_canonical_facts_in_batches(session: Session, logger: Logger):
    """Updates canonical facts columns from the canonical_facts JSONB column using batched processing."""
    batch_size = int(os.getenv("CANONICAL_FACTS_MIGRATION_BATCH_SIZE", 5000))
    # Initialize cursor for DESC pagination. These are "max" values to start from the top.
    last_modified_on = "9999-12-31 23:59:59+00"
    last_id = "ffffffff-ffff-ffff-ffff-ffffffffffff"
    total_rows_updated = 0

    logger.info(
        f"Starting canonical facts migration using (last_modified_on, id) index with a batch size of {batch_size} rows."
    )

    while True:
        batch_start_time = time.perf_counter()
        logger.info(f"Fetching next batch of hosts with last_modified_on before: {last_modified_on} - {last_id}")

        # Step 1: Fetch the next batch using the descending index.
        # The ORDER BY clause must match the index definition for efficiency.
        batch_to_process = session.execute(
            text(
                f"""
                SELECT id, modified_on FROM {INVENTORY_SCHEMA}.hosts
                WHERE (modified_on, id) < (:last_modified_on, :last_id)
                    AND canonical_facts IS NOT NULL
                ORDER BY last_check_in DESC, id DESC
                LIMIT :batch_size;
                """
            ),
            {"last_modified_on": last_modified_on, "last_id": last_id, "batch_size": batch_size},
        ).fetchall()

        if not batch_to_process:
            logger.info("No more hosts to process. Canonical facts migration complete.")
            break

        id_list = [row[0] for row in batch_to_process]
        logger.info(f"Processing batch of {len(id_list)} hosts...")

        # Step 2: Update canonical facts columns for the current batch
        # Convert UUID list to string format for the query
        id_list_str = [str(host_id) for host_id in id_list]

        update_sql = f"""
            UPDATE {INVENTORY_SCHEMA}.hosts
            SET
                insights_id = COALESCE((canonical_facts->>'insights_id')::uuid, '00000000-0000-0000-0000-000000000000'),
                subscription_manager_id = canonical_facts ->> 'subscription_manager_id',
                satellite_id = canonical_facts ->> 'satellite_id',
                fqdn = canonical_facts ->> 'fqdn',
                bios_uuid = canonical_facts ->> 'bios_uuid',
                ip_addresses = canonical_facts -> 'ip_addresses',
                mac_addresses = canonical_facts -> 'mac_addresses',
                provider_id = canonical_facts ->> 'provider_id',
                provider_type = canonical_facts ->> 'provider_type'
            WHERE id IN :id_list
                AND canonical_facts IS NOT NULL;
        """

        result = session.execute(text(update_sql), {"id_list": tuple(id_list_str)})
        rows_affected = result.rowcount

        # Update loop variables with the last row from the processed batch
        last_row = batch_to_process[-1]
        last_modified_on = last_row[1]
        last_id = last_row[0]

        total_rows_updated += rows_affected
        batch_duration = time.perf_counter() - batch_start_time

        logger.info(
            f"Batch complete in {batch_duration:.2f}s. "
            f"Updated {rows_affected} rows in this batch. "
            f"Total rows updated so far: {total_rows_updated}. "
            f"Next batch starts before: {last_modified_on}"
        )

        session.commit()

    logger.info(f"Successfully finished updating canonical facts. Total rows updated: {total_rows_updated}.")


def run(logger: Logger, session: Session, application: FlaskApp):
    """Main execution function."""
    try:
        with application.app.app_context():
            drop_indexes(session, logger)
            update_canonical_facts_in_batches(session, logger)
            recreate_indexes(session, logger)
    except Exception:
        logger.exception("A critical error occurred during the canonical facts migration job.")
        raise
    finally:
        logger.info("Closing database session.")
        session.close()


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)

    if SUSPEND_JOB:
        logger.info("SUSPEND_CANONICAL_FACTS_MIGRATION is set to true; exiting job.")
        sys.exit(0)

    job_type = "Canonical facts migration"
    sys.excepthook = partial(excepthook, logger, job_type)

    _, session, _, _, _, application = job_setup((), PROMETHEUS_JOB)

    run(logger, session, application)

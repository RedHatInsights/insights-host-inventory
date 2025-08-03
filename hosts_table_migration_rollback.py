#!/usr/bin/python
# ruff: noqa: E501
import os
import sys
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

PROMETHEUS_JOB = "hosts-table-rollback-sync"
LOGGER_NAME = "hosts_table_rollback_sync"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB
SUSPEND_JOB = os.environ.get("SUSPEND_JOB", "true").lower() == "true"

"""
This job is intended to be run ONLY before an emergency rollback of the hosts
table partitioning migration. It synchronizes any data changes that occurred on
the live partitioned tables (e.g., 'hosts') back to the original backup tables
(e.g., 'hosts_old').
"""


def sync_new_and_updated_hosts(session: Session, logger: Logger, since_timestamp: str):
    """
    Finds all hosts in the live partitioned table that were created or modified
    since the cutover and UPSERTs them into the backup '_old' table. This also
    syncs their corresponding group memberships.
    """
    logger.info(f"Syncing new/updated hosts from 'hosts' to 'hosts_old' modified since {since_timestamp}...")

    batch_size = int(os.getenv("HOSTS_TABLE_MIGRATION_BATCH_SIZE", 5000))
    last_modified_on = since_timestamp
    last_id = "00000000-0000-0000-0000-000000000000"
    total_synced = 0

    while True:
        logger.info(f"Fetching next batch of changes after: {last_modified_on} - {last_id}")

        # Paginate through the LIVE PARTITIONED 'hosts' table to find all changes since the cutover
        batch_to_process = session.execute(
            text(f"""
                SELECT id, org_id, modified_on FROM {INVENTORY_SCHEMA}.hosts
                WHERE modified_on >= :since_timestamp
                  AND (modified_on, id) > (:last_modified_on, :last_id)
                ORDER BY modified_on, id
                LIMIT :batch_size;
            """),
            {
                "since_timestamp": since_timestamp,
                "last_modified_on": last_modified_on,
                "last_id": last_id,
                "batch_size": batch_size,
            },
        ).fetchall()

        if not batch_to_process:
            break

        id_list = [row[0] for row in batch_to_process]

        # Step 1: UPSERT the main host data back to the original 'hosts_old' table.
        # The target 'hosts_old' table has a single-column PK on 'id'.
        upsert_sql = f"""
            INSERT INTO {INVENTORY_SCHEMA}.hosts_old (
                id, org_id, account, display_name, ansible_host, created_on, modified_on, facts, tags,
                tags_alt, system_profile_facts, groups, last_check_in, stale_timestamp, deletion_timestamp,
                stale_warning_timestamp, reporter, per_reporter_staleness, canonical_facts
            )
            SELECT
                id, org_id, account, display_name, ansible_host, created_on, modified_on, facts, tags,
                tags_alt, system_profile_facts, groups, last_check_in, stale_timestamp, deletion_timestamp,
                stale_warning_timestamp, reporter, per_reporter_staleness, canonical_facts
            FROM {INVENTORY_SCHEMA}.hosts
            WHERE id = ANY(:id_list)
            ON CONFLICT (id) DO UPDATE SET
                org_id = EXCLUDED.org_id,
                account = EXCLUDED.account,
                display_name = EXCLUDED.display_name,
                ansible_host = EXCLUDED.ansible_host,
                modified_on = EXCLUDED.modified_on,
                facts = EXCLUDED.facts,
                tags = EXCLUDED.tags,
                tags_alt = EXCLUDED.tags_alt,
                system_profile_facts = EXCLUDED.system_profile_facts,
                groups = EXCLUDED.groups,
                last_check_in = EXCLUDED.last_check_in,
                stale_timestamp = EXCLUDED.stale_timestamp,
                deletion_timestamp = EXCLUDED.deletion_timestamp,
                stale_warning_timestamp = EXCLUDED.stale_warning_timestamp,
                reporter = EXCLUDED.reporter,
                per_reporter_staleness = EXCLUDED.per_reporter_staleness,
                canonical_facts = EXCLUDED.canonical_facts;
        """
        session.execute(text(upsert_sql), {"id_list": id_list})

        # Step 2: Sync the hosts_groups_old table using a "delete-then-insert" strategy.
        # First, remove all old associations for this batch of hosts from the backup table.
        session.execute(
            text(f"DELETE FROM {INVENTORY_SCHEMA}.hosts_groups_old WHERE host_id = ANY(:id_list);"),
            {"id_list": id_list},
        )

        # Second, re-insert the correct associations by reading from the live partitioned table's JSONB.
        reinsert_groups_sql = f"""
            INSERT INTO {INVENTORY_SCHEMA}.hosts_groups_old (host_id, group_id)
            SELECT
                h.id,
                (g.value ->> 'id')::uuid
            FROM
                {INVENTORY_SCHEMA}.hosts h,
                jsonb_array_elements(h.groups) AS g(value)
            WHERE
                h.id = ANY(:id_list)
                AND jsonb_typeof(h.groups) = 'array' AND jsonb_array_length(h.groups) > 0;
        """
        session.execute(text(reinsert_groups_sql), {"id_list": id_list})

        session.commit()

        last_row = batch_to_process[-1]
        last_modified_on = last_row[2]
        last_id = last_row[0]
        total_synced += len(id_list)
        logger.info(f"Synced {len(id_list)} new/updated hosts and their groups. Total so far: {total_synced}")

    logger.info("Finished syncing new and updated hosts.")


def sync_deleted_hosts(session: Session, logger: Logger, since_timestamp: str):
    """
    Finds hosts that exist in the backup table but are missing from the live table,
    indicating they were deleted while the partitioned table was live.
    """
    logger.info(f"Checking for hosts deleted since {since_timestamp}...")

    # This query finds IDs in 'hosts_old' that are not present in the live 'hosts' table.
    delete_sql = f"""
        DELETE FROM {INVENTORY_SCHEMA}.hosts_old
        WHERE id IN (
            SELECT h_old.id
            FROM {INVENTORY_SCHEMA}.hosts_old h_old
            LEFT JOIN {INVENTORY_SCHEMA}.hosts h_new ON h_old.id = h_new.id
            WHERE h_new.id IS NULL
        );
    """
    result = session.execute(text(delete_sql), {"since_timestamp": since_timestamp})
    session.commit()
    logger.info(f"{result.rowcount} deleted hosts were synchronized back to the original table.")


def run(logger: Logger, session: Session, application: FlaskApp):
    """Main execution function."""

    # This timestamp should be the time your original maintenance window started.
    # It ensures we only sync changes that happened after the cutover.
    since_timestamp = os.environ.get("SYNC_SINCE_TIMESTAMP")
    if not since_timestamp:
        raise ValueError("SYNC_SINCE_TIMESTAMP environment variable must be set (e.g., '2025-08-03 08:00:00+00')")

    try:
        with application.app.app_context():
            sync_new_and_updated_hosts(session, logger, since_timestamp)
            sync_deleted_hosts(session, logger, since_timestamp)
    except Exception:
        logger.exception("A critical error occurred during the rollback sync job.")
        raise
    finally:
        logger.info("Closing database session.")
        session.close()


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)

    if SUSPEND_JOB:
        logger.info("SUSPEND_JOB is set to true; exiting job.")
        sys.exit(0)

    job_type = "Hosts table post-rollback synchronizer"
    sys.excepthook = partial(excepthook, logger, job_type)

    config, session, _, _, _, application = job_setup((), PROMETHEUS_JOB)

    run(logger, session, application)

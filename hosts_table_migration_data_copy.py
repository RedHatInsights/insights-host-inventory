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

# Single Source of Truth for Index DDL
INDEX_DEFINITIONS = {
    # hosts_new indexes
    "idx_hosts_modified_on_id": "CREATE INDEX {index_name} ON {schema}.hosts_new (modified_on DESC, id DESC);",
    "idx_hosts_insights_id": "CREATE INDEX {index_name} ON {schema}.hosts_new (insights_id);",
    "idx_hosts_subscription_manager_id": "CREATE INDEX {index_name} ON {schema}.hosts_new (subscription_manager_id);",
    "idx_hosts_canonical_facts_gin": "CREATE INDEX {index_name} ON {schema}.hosts_new USING gin (canonical_facts jsonb_path_ops);",
    "idx_hosts_groups_gin": "CREATE INDEX {index_name} ON {schema}.hosts_new USING gin (groups);",
    "idx_hosts_host_type": "CREATE INDEX {index_name} ON {schema}.hosts_new ((system_profile_facts ->> 'host_type'));",
    "idx_hosts_cf_insights_id": "CREATE INDEX {index_name} ON {schema}.hosts_new ((canonical_facts ->> 'insights_id'));",
    "idx_hosts_cf_subscription_manager_id": "CREATE INDEX {index_name} ON {schema}.hosts_new ((canonical_facts ->> 'subscription_manager_id'));",
    "idx_hosts_mssql": "CREATE INDEX {index_name} ON {schema}.hosts_new ((system_profile_facts ->> 'mssql'));",
    "idx_hosts_ansible": "CREATE INDEX {index_name} ON {schema}.hosts_new ((system_profile_facts ->> 'ansible'));",
    "idx_hosts_sap_system": "CREATE INDEX {index_name} ON {schema}.hosts_new (((system_profile_facts ->> 'sap_system')::boolean));",
    "idx_hosts_host_type_modified_on_org_id": "CREATE INDEX {index_name} ON {schema}.hosts_new (org_id, modified_on, (system_profile_facts ->> 'host_type'));",
    "idx_hosts_bootc_status": "CREATE INDEX {index_name} ON {schema}.hosts_new (org_id) WHERE ((system_profile_facts -> 'bootc_status' -> 'booted' ->> 'image_digest') IS NOT NULL);",
    "idx_hosts_operating_system_multi": """
        CREATE INDEX {index_name} ON {schema}.hosts_new (
            ((system_profile_facts -> 'operating_system' ->> 'name')),
            ((system_profile_facts -> 'operating_system' ->> 'major')::integer),
            ((system_profile_facts -> 'operating_system' ->> 'minor')::integer),
            (system_profile_facts ->> 'host_type'),
            modified_on,
            org_id
        ) WHERE (system_profile_facts -> 'operating_system') IS NOT NULL;
    """,
    # hosts_groups_new indexes
    "idx_hosts_groups_forward": "CREATE INDEX {index_name} ON {schema}.hosts_groups_new (org_id, host_id, group_id);",
    "idx_hosts_groups_reverse": "CREATE INDEX {index_name} ON {schema}.hosts_groups_new (org_id, group_id, host_id);",
}

"""
This job copies all historical data from the original 'hosts' table into the
new partitioned tables ('hosts_new' and 'hosts_groups_new'). It processes
data in batches to manage memory and WAL size.

This script should only be run during a planned maintenance window.
"""


def truncate_new_tables(session: Session, logger: Logger):
    """Truncates the target tables to ensure they are empty before copying."""
    logger.warning("Truncating hosts_new and hosts_groups_new tables...")
    session.execute(text(f"TRUNCATE TABLE {INVENTORY_SCHEMA}.hosts_new CASCADE;"))
    session.execute(text(f"TRUNCATE TABLE {INVENTORY_SCHEMA}.hosts_groups_new CASCADE;"))
    session.commit()
    logger.info("Target tables have been truncated.")


def update_bios_uuid_column_type(session: Session, logger: Logger):
    """
    Alters the bios_uuid column in hosts_new to VARCHAR(255).
    This operation is idempotent and will not run if the column is already correct.
    """
    logger.info("Checking data type of 'bios_uuid' column in hosts_new table...")

    # Query the information schema to get the current character limit
    check_sql = text("""
                     SELECT character_maximum_length
                     FROM information_schema.columns
                     WHERE table_schema = :schema
                       AND table_name = 'hosts_new'
                       AND column_name = 'bios_uuid';
                     """)

    try:
        current_length = session.execute(check_sql, {"schema": INVENTORY_SCHEMA}).scalar_one_or_none()

        if current_length == 255:
            logger.info("'bios_uuid' column is already VARCHAR(255). No action needed.")
            return

        logger.warning(f"Current 'bios_uuid' type is VARCHAR({current_length})... updating to VARCHAR(255).")
        alter_sql = text(f"ALTER TABLE {INVENTORY_SCHEMA}.hosts_new ALTER COLUMN bios_uuid TYPE VARCHAR(255);")

        session.execute(alter_sql)
        session.commit()
        logger.info("'bios_uuid' column has been successfully updated to VARCHAR(255).")

    except Exception:
        logger.error("Failed to alter 'bios_uuid' column. Rolling back.")
        session.rollback()
        raise


def update_per_reporter_staleness_default(session: Session, logger: Logger):
    """
    Alters the per_reporter_staleness column in hosts_new to have a default
    value of an empty JSONB object. This operation is idempotent.
    """
    logger.info("Checking default value of 'per_reporter_staleness' column in hosts_new table...")

    check_sql = text(
        """
        SELECT column_default
        FROM information_schema.columns
        WHERE table_schema = :schema
          AND table_name = 'hosts_new'
          AND column_name = 'per_reporter_staleness';
    """
    )

    try:
        column_default = session.execute(check_sql, {"schema": INVENTORY_SCHEMA}).scalar_one_or_none()

        if column_default == "'{}'::jsonb":
            logger.info("'per_reporter_staleness' column already has the correct default value. No action needed.")
            return

        logger.warning(f"Current default is '{column_default}'. Setting default to '{{}}'::jsonb.")
        alter_default_sql = text(
            f"ALTER TABLE {INVENTORY_SCHEMA}.hosts_new ALTER COLUMN per_reporter_staleness SET DEFAULT '{{}}'::jsonb;"
        )
        session.execute(alter_default_sql)
        session.commit()
        logger.info("'per_reporter_staleness' column default has been set successfully.")

    except Exception:
        logger.error("Failed to set default for 'per_reporter_staleness' column. Rolling back.")
        session.rollback()
        raise


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


def copy_data_in_batches(session: Session, logger: Logger):
    """Copies data using the existing (modified_on, id) index for keyset pagination."""
    batch_size = int(os.getenv("HOSTS_TABLE_MIGRATION_BATCH_SIZE", 5000))
    # Initialize cursor for DESC pagination. These are "max" values to start from the top.
    last_modified_on = "9999-12-31 23:59:59+00"
    last_id = "ffffffff-ffff-ffff-ffff-ffffffffffff"
    total_rows_copied = 0

    logger.info(
        f"Starting batched data migration using (modified_on, id) index with a batch size of {batch_size} rows."
    )

    while True:
        batch_start_time = time.perf_counter()
        logger.info(f"Fetching next batch of hosts modified before: {last_modified_on} - {last_id}")

        # Step 1: Fetch the next batch using the descending index.
        # The ORDER BY clause must match the index definition for efficiency.
        batch_to_process = session.execute(
            text(
                f"""
                SELECT id, modified_on FROM {INVENTORY_SCHEMA}.hosts
                WHERE (modified_on, id) < (:last_modified_on, :last_id)
                ORDER BY modified_on DESC, id DESC
                LIMIT :batch_size;
                """
            ),
            {"last_modified_on": last_modified_on, "last_id": last_id, "batch_size": batch_size},
        ).fetchall()

        if not batch_to_process:
            logger.info("No more hosts to process. Data migration complete.")
            break

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
        last_modified_on = last_row[1]
        last_id = last_row[0]

        total_rows_copied += len(id_list)
        batch_duration = time.perf_counter() - batch_start_time

        logger.info(
            f"Batch complete in {batch_duration:.2f}s. "
            f"Total rows copied so far: {total_rows_copied}. "
            f"Next batch starts before: {last_modified_on}"
        )

        session.commit()

    logger.info(f"Successfully finished copying all data. Total rows processed: {total_rows_copied}.")


def run(logger: Logger, session: Session, application: FlaskApp):
    """Main execution function."""
    try:
        with application.app.app_context():
            truncate_new_tables(session, logger)
            update_bios_uuid_column_type(session, logger)
            update_per_reporter_staleness_default(session, logger)
            drop_indexes(session, logger)
            copy_data_in_batches(session, logger)
            recreate_indexes(session, logger)
    except Exception:
        logger.exception("A critical error occurred during the data copy job.")
        raise
    finally:
        logger.info("Closing database session.")
        session.close()


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)

    if SUSPEND_JOB:
        logger.info("SUSPEND_JOB is set to true; exiting job.")
        sys.exit(0)

    job_type = "Hosts partitioned tables full data copy"
    sys.excepthook = partial(excepthook, logger, job_type)

    _, session, _, _, _, application = job_setup((), PROMETHEUS_JOB)

    run(logger, session, application)

#!/usr/bin/python3
# ruff: noqa: E501
import os
import sys
from functools import partial
from logging import Logger

from connexion import FlaskApp
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import Config
from app.environment import RuntimeEnvironment
from app.logging import get_logger
from app.models.constants import INVENTORY_SCHEMA
from jobs.common import excepthook
from jobs.common import job_setup
from lib.db import session_guard

PROMETHEUS_JOB = "remove_null_values_in_workloads_fields_data"
LOGGER_NAME = "remove_null_values_in_workloads_fields_data"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB
SUSPEND_JOB = os.environ.get("SUSPEND_JOB", "true").lower() == "true"


def _count_affected_rows(session: Session) -> int:
    """
    Count rows that need to be updated in system_profiles_dynamic.

    Args:
        session: Database session

    Returns:
        Number of rows with JSON null values in workloads
    """
    count_sql = f"""
        SELECT COUNT(*)
        FROM {INVENTORY_SCHEMA}.system_profiles_dynamic
        WHERE workloads IS NOT NULL
            AND EXISTS (
                SELECT 1
                FROM jsonb_each(workloads) AS wl(key, value),
                     jsonb_each(value) AS fields(field_key, field_value)
                WHERE field_value = 'null'::jsonb
            )
    """

    result = session.execute(text(count_sql))
    return result.scalar()


def _update_system_profiles_dynamic_batch(session: Session, batch_size: int) -> int:
    """
    Update a batch of system_profiles_dynamic rows with JSON null values in workloads.

    Uses a CTE to identify affected rows and limit the update to batch_size rows.
    This prevents long-running transactions and table locks on very large tables.

    Args:
        session: Database session
        batch_size: Maximum number of rows to update in this batch

    Returns:
        Number of rows updated
    """
    sql_update_spd_batch = f"""
        WITH affected_profiles AS (
            SELECT host_id
            FROM {INVENTORY_SCHEMA}.system_profiles_dynamic
            WHERE workloads IS NOT NULL
                AND EXISTS (
                    SELECT 1
                    FROM jsonb_each(workloads) AS wl(key, value),
                         jsonb_each(value) AS fields(field_key, field_value)
                    WHERE field_value = 'null'::jsonb
                )
            LIMIT :batch_size
        )
        UPDATE {INVENTORY_SCHEMA}.system_profiles_dynamic spd
        SET workloads = COALESCE(
            (
                SELECT jsonb_object_agg(key, jsonb_strip_nulls(value))
                FROM jsonb_each(workloads)
                WHERE value IS NOT NULL
            ),
            '{{}}'::jsonb
        )
        FROM affected_profiles ap
        WHERE spd.host_id = ap.host_id
    """

    result = session.execute(text(sql_update_spd_batch), {"batch_size": batch_size})
    return result.rowcount


def remove_null_values_spf_workloads_fields(session: Session, logger: Logger, config: Config, dry_run: bool = False):
    """
    Remove fields with null values in the 'workloads' section of system profile facts.

    Processes updates in batches to prevent long-running transactions and table locks.
    Safe for tables with millions of rows.

    Args:
        session: Database session
        logger: Logger instance
        config: Application configuration (provides batch size)
        dry_run: If True, only count affected rows without making changes
    """
    batch_size = config.script_chunk_size

    logger.info("Starting workloads null fields removal job")
    logger.info(f"Batch size: {batch_size}")
    logger.info(f"Dry run mode: {dry_run}")

    # --- Process 'system_profiles_dynamic' table ---
    logger.info("Analyzing 'system_profiles_dynamic' table...")
    total_spd_to_update = _count_affected_rows(session)
    logger.info(f"Found {total_spd_to_update} dynamic profiles with JSON null values in workloads")

    if dry_run:
        logger.info("[DRY RUN] Would update system_profiles_dynamic table in batches")
    else:
        total_spd_updated = 0
        batch_num = 0

        while total_spd_updated < total_spd_to_update:
            batch_num += 1
            logger.info(f"Processing system_profiles_dynamic batch {batch_num}...")

            with session_guard(session, close=False):
                rows_updated = _update_system_profiles_dynamic_batch(session, batch_size)
                total_spd_updated += rows_updated

            logger.info(
                f"Batch {batch_num} complete: updated {rows_updated} profiles "
                f"({total_spd_updated}/{total_spd_to_update} total)"
            )

            # If no rows were updated, we're done
            if rows_updated == 0:
                logger.info("No more profiles to update")
                break

        logger.info(f"System profiles dynamic table complete: updated {total_spd_updated} rows")


def run(config: Config, logger: Logger, session: Session, application: FlaskApp):
    """
    Main execution function.

    Args:
        config: Application configuration
        logger: Logger instance
        session: Database session
        application: Flask application instance
    """
    dry_run = config.dry_run

    try:
        with application.app.app_context():
            logger.info("Starting job: remove null values in workloads fields")
            if dry_run:
                logger.info("=" * 60)
                logger.info("DRY RUN MODE - No changes will be made to the database")
                logger.info("=" * 60)

            remove_null_values_spf_workloads_fields(session, logger, config, dry_run)

            if not dry_run:
                logger.info("Successfully committed all workloads cleanup changes")
            else:
                logger.info("=" * 60)
                logger.info("DRY RUN COMPLETE - No changes were made")
                logger.info("=" * 60)

    except Exception:
        logger.exception("A critical error occurred during workloads cleanup job")
        if not dry_run:
            session.rollback()
        raise
    finally:
        logger.info("Closing database session")
        session.close()


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)

    if SUSPEND_JOB:
        logger.info("SUSPEND_JOB is set to true; exiting job")
        sys.exit(0)

    job_type = "Remove workloads fields data with null values"
    sys.excepthook = partial(excepthook, logger, job_type)

    config, session, _, _, _, application = job_setup((), PROMETHEUS_JOB)

    try:
        run(config, logger, session, application)
    except Exception as e:
        logger.exception(f"Job failed: {e}")
        sys.exit(1)

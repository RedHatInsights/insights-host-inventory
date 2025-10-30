#!/usr/bin/env python3

"""
Job to backfill missing culled_timestamp fields in per_reporter_staleness.

This job finds all hosts that have per_reporter_staleness entries missing
the culled_timestamp field and populates them using the existing staleness
calculation logic. This fixes the registered_with filter issue where hosts
with legacy data (missing culled_timestamp) were excluded from both positive
and negative filter results.

Usage:
    python jobs/backfill_per_reporter_culled_timestamps.py

Environment variables:
    DRY_RUN=true - Run in dry-run mode (default: true)
    SCRIPT_CHUNK_SIZE=1000 - Number of hosts to process per batch (default: 1000)
"""

import sys
from functools import partial
from logging import Logger

from connexion import FlaskApp
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.orm import attributes as orm

from api.staleness_query import get_staleness_obj
from app import create_app
from app.common import inventory_config
from app.config import Config
from app.culling import Timestamps
from app.environment import RuntimeEnvironment
from app.logging import get_logger
from app.logging import threadctx
from app.models import Host
from app.serialization import serialize_staleness_to_dict
from app.staleness_serialization import get_reporter_staleness_timestamps
from jobs.common import excepthook
from jobs.common import job_setup
from lib.db import session_guard

PROMETHEUS_JOB = "inventory-backfill-per-reporter-culled-timestamps"
LOGGER_NAME = "backfill_per_reporter_culled_timestamps"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB

application = create_app(RUNTIME_ENVIRONMENT)
app = application.app


def _count_hosts_missing_culled_timestamps(session: Session) -> int:
    """
    Count hosts that have per_reporter_staleness entries missing culled_timestamp.

    Args:
        session: Database session

    Returns:
        Total number of hosts with missing culled_timestamp fields
    """
    return (
        session.query(Host)
        .filter(
            text("""
            per_reporter_staleness IS NOT NULL
            AND EXISTS (
                SELECT 1
                FROM jsonb_each(per_reporter_staleness) AS reporter_entry
                WHERE NOT (reporter_entry.value ? 'culled_timestamp')
                AND reporter_entry.value ? 'last_check_in'
            )
        """),
        )
        .count()
    )


def _get_hosts_missing_culled_timestamps(
    session: Session, chunk_size: int, last_host_id: str | None = None
) -> list[Host]:
    """
    Query for hosts that have per_reporter_staleness entries missing culled_timestamp.

    Args:
        session: Database session
        chunk_size: Number of hosts to return
        last_host_id: ID of the last processed host for pagination

    Returns:
        List of Host objects with missing culled_timestamp fields
    """
    query = session.query(Host).filter(
        text("""
            per_reporter_staleness IS NOT NULL
            AND EXISTS (
                SELECT 1
                FROM jsonb_each(per_reporter_staleness) AS reporter_entry
                WHERE NOT (reporter_entry.value ? 'culled_timestamp')
                AND reporter_entry.value ? 'last_check_in'
            )
        """),
    )

    if last_host_id:
        query = query.filter(Host.id > last_host_id)

    return query.order_by(Host.id).limit(chunk_size).all()


def _update_host_per_reporter_culled_timestamps(host: Host, logger: Logger, dry_run: bool = False) -> bool:
    """
    Update missing culled_timestamp fields for a single host.

    Args:
        host: Host object to update
        logger: Logger instance
        dry_run: If True, only log what would be updated

    Returns:
        True if the host was updated, False otherwise
    """
    if not host.per_reporter_staleness:
        return False

    # Count reporters missing culled_timestamp
    reporters_missing_culled = []
    for reporter_name, reporter_data in host.per_reporter_staleness.items():
        if "culled_timestamp" not in reporter_data:
            reporters_missing_culled.append(reporter_name)

    if not reporters_missing_culled:
        return False

    if dry_run:
        logger.info(
            f"[DRY RUN] Would update Host {host.id} reporters {reporters_missing_culled} with culled_timestamp"
        )
        return True

    try:
        # Get staleness configuration for the host's org
        staleness_obj = get_staleness_obj(host.org_id)
        staleness = serialize_staleness_to_dict(staleness_obj)
        staleness_ts = Timestamps.from_config(inventory_config())

        for reporter in reporters_missing_culled:
            timestamps = get_reporter_staleness_timestamps(host, staleness_ts, staleness, reporter)

            host.per_reporter_staleness[reporter]["culled_timestamp"] = timestamps["culled_timestamp"].isoformat()
            orm.flag_modified(host, "per_reporter_staleness")

            logger.debug(f"Updated Host {host.id} reporter {reporter} with culled_timestamp")
        host.save()
        return True
    except Exception as e:
        logger.error(f"Failed to update Host {host.id}: {e}")
        return False


def run(config: Config, logger: Logger, session: Session, application: FlaskApp) -> None:
    """
    Main job execution function.

    Args:
        config: Application configuration
        logger: Logger instance
        session: Database session
        application: Flask application instance
    """
    dry_run = config.dry_run
    chunk_size = config.script_chunk_size

    if dry_run:
        logger.info(f"Running {PROMETHEUS_JOB} in dry-run mode. No data will be modified.")
    else:
        logger.info(f"Running {PROMETHEUS_JOB} in update mode. Data WILL be modified.")

    with application.app.app_context():
        threadctx.request_id = None

        # In dry-run mode, just count and exit immediately
        if dry_run:
            logger.debug("Executing count query for hosts missing culled_timestamp...")
            total_hosts = _count_hosts_missing_culled_timestamps(session)
            logger.info(f"Dry-run complete. Found {total_hosts} hosts that would be updated.")
            logger.info("This was a dry run - no actual changes were made to the database.")

            # Additional debug: check total hosts in table for context
            total_hosts_in_table = session.query(Host).count()
            logger.debug(f"Total hosts in table: {total_hosts_in_table}")

            # Check how many have non-NULL per_reporter_staleness
            hosts_with_prs = session.query(Host).filter(Host.per_reporter_staleness.isnot(None)).count()
            logger.debug(f"Hosts with non-NULL per_reporter_staleness: {hosts_with_prs}")
            return

        total_hosts_processed = 0
        total_hosts_updated = 0
        last_host_id = None

        while True:
            # Get the next batch of hosts
            hosts = _get_hosts_missing_culled_timestamps(session, chunk_size, last_host_id)

            logger.info(f"Found {len(hosts)} hosts to process")

            if not hosts:
                logger.info("No more hosts to process")
                break

            batch_hosts_updated = 0

            with session_guard(session):
                for host in hosts:
                    if _update_host_per_reporter_culled_timestamps(host, logger, dry_run):
                        batch_hosts_updated += 1

                last_host_id = hosts[-1].id
                session.flush()

            total_hosts_processed += len(hosts)
            total_hosts_updated += batch_hosts_updated

            logger.info(f"Processed batch of {len(hosts)} hosts, updated {batch_hosts_updated} hosts")

        logger.info(
            f"Job completed. Total hosts processed: {total_hosts_processed}, "
            f"total hosts updated: {total_hosts_updated}"
        )


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)
    job_type = "Backfill per-reporter culled timestamps"
    sys.excepthook = partial(excepthook, logger, job_type)

    config, session, _, _, _, application = job_setup((), PROMETHEUS_JOB)

    try:
        run(config, logger, session, application)
    except Exception as e:
        logger.exception(f"Job failed: {e}")
        sys.exit(1)
    finally:
        session.close()

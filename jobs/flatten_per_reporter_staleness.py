#!/usr/bin/env python3

"""
Job to flatten per_reporter_staleness structure from nested to flat format.

This job transforms per_reporter_staleness from the nested format:
    {"reporter": {"last_check_in": "...", "stale_timestamp": "...", ...}}
to the flat format:
    {"reporter": "ISO timestamp"}

Only the last_check_in timestamp is preserved; staleness timestamps are
computed on-the-fly during serialization.

The job processes hosts org-by-org to take advantage of table partitioning.

Usage:
    python jobs/flatten_per_reporter_staleness.py

Environment variables:
    DRY_RUN=true - Run in dry-run mode (default: true)
    SCRIPT_CHUNK_SIZE=1000 - Number of hosts to process per batch (default: 1000)
    ORG_ID=<org_id> - Process specific org only (optional, for testing)
"""

import sys
from functools import partial
from logging import Logger

from connexion import FlaskApp
from sqlalchemy import distinct
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import create_app
from app.config import Config
from app.environment import RuntimeEnvironment
from app.logging import get_logger
from app.logging import threadctx
from app.models import Host
from jobs.common import excepthook
from jobs.common import job_setup
from lib.db import session_guard

PROMETHEUS_JOB = "inventory-flatten-per-reporter-staleness"
LOGGER_NAME = "flatten_per_reporter_staleness"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB

application = create_app(RUNTIME_ENVIRONMENT)
app = application.app


def _get_org_ids(session: Session) -> list[str]:
    """
    Get all distinct org_ids from the hosts table.

    Args:
        session: Database session

    Returns:
        List of org_id strings
    """
    return [org_id for (org_id,) in session.query(distinct(Host.org_id)).all()]


def _count_hosts_with_nested_format(session: Session, org_id: str) -> int:
    """
    Count hosts in a specific org that have nested per_reporter_staleness format.
    Used only in dry-run mode.

    Args:
        session: Database session
        org_id: Organization ID to filter by

    Returns:
        Number of hosts with nested format
    """
    return (
        session.query(Host)
        .filter(
            Host.org_id == org_id,
            text("""
            EXISTS (
                SELECT 1
                FROM jsonb_each(per_reporter_staleness) AS reporter_entry
                WHERE jsonb_typeof(reporter_entry.value) = 'object'
                AND reporter_entry.value ? 'last_check_in'
            )
        """),
        )
        .count()
    )


def _get_hosts_with_nested_format(
    session: Session, org_id: str, chunk_size: int, last_host_id: str | None = None
) -> list[Host]:
    """
    Query for hosts in a specific org with nested per_reporter_staleness format.

    Args:
        session: Database session
        org_id: Organization ID to filter by
        chunk_size: Number of hosts to return
        last_host_id: ID of the last processed host for pagination

    Returns:
        List of Host objects with nested format
    """
    query = session.query(Host).filter(
        Host.org_id == org_id,
        text("""
            EXISTS (
                SELECT 1
                FROM jsonb_each(per_reporter_staleness) AS reporter_entry
                WHERE jsonb_typeof(reporter_entry.value) = 'object'
                AND reporter_entry.value ? 'last_check_in'
            )
        """),
    )

    if last_host_id:
        query = query.filter(Host.id > last_host_id)

    return query.order_by(Host.id).limit(chunk_size).all()


def _flatten_host_per_reporter_staleness(host: Host, logger: Logger, dry_run: bool = False) -> bool:
    """
    Flatten per_reporter_staleness for a single host.

    Transforms from:
        {"reporter": {"last_check_in": "2025-01-15T10:00:00Z", "stale_timestamp": "...", ...}}
    To:
        {"reporter": "2025-01-15T10:00:00Z"}

    Args:
        host: Host object to update
        logger: Logger instance
        dry_run: If True, only log what would be updated

    Returns:
        True if the host was updated, False otherwise
    """
    if not host.per_reporter_staleness:
        return False

    # Check if any reporters need flattening
    needs_flattening = False
    for _reporter_name, reporter_data in host.per_reporter_staleness.items():
        if isinstance(reporter_data, dict) and "last_check_in" in reporter_data:
            needs_flattening = True
            break

    if not needs_flattening:
        return False

    if dry_run:
        reporters_to_flatten = [
            name
            for name, data in host.per_reporter_staleness.items()
            if isinstance(data, dict) and "last_check_in" in data
        ]
        logger.info(f"[DRY RUN] Would flatten Host {host.id} reporters {reporters_to_flatten}")
        return True

    try:
        # Transform the structure
        flattened = {}
        for reporter_name, reporter_data in host.per_reporter_staleness.items():
            if isinstance(reporter_data, dict) and "last_check_in" in reporter_data:
                # Extract only last_check_in timestamp
                flattened[reporter_name] = reporter_data["last_check_in"]
            else:
                # Already flat or invalid, keep as is
                flattened[reporter_name] = reporter_data

        host.per_reporter_staleness = flattened
        logger.debug(f"Flattened Host {host.id} per_reporter_staleness")
        return True

    except Exception as e:
        logger.error(f"Failed to flatten Host {host.id}: {e}")
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
    target_org_id = config.org_id if hasattr(config, "org_id") else None

    if dry_run:
        logger.info(f"Running {PROMETHEUS_JOB} in dry-run mode. No data will be modified.")
    else:
        logger.info(f"Running {PROMETHEUS_JOB} in update mode. Data WILL be modified.")

    with application.app.app_context():
        threadctx.request_id = None

        # Get list of org_ids to process
        if target_org_id:
            org_ids = [target_org_id]
            logger.info(f"Processing single org: {target_org_id}")
        else:
            org_ids = _get_org_ids(session)
            logger.info(f"Found {len(org_ids)} organizations to process")

        total_orgs_processed = 0
        total_hosts_processed = 0
        total_hosts_updated = 0

        # Process each org separately to leverage partitioning
        for org_id in org_ids:
            logger.info(f"Processing org_id: {org_id}")

            # In dry-run mode, just count for this org
            if dry_run:
                org_host_count = _count_hosts_with_nested_format(session, org_id)
                logger.info(f"Org {org_id}: Found {org_host_count} hosts with nested format")
                total_hosts_processed += org_host_count
                total_orgs_processed += 1
                continue

            # Process hosts for this org in chunks
            last_host_id = None
            org_hosts_processed = 0
            org_hosts_updated = 0

            while True:
                # Get the next batch of hosts for this org
                hosts = _get_hosts_with_nested_format(session, org_id, chunk_size, last_host_id)

                if not hosts:
                    break

                batch_hosts_updated = 0

                with session_guard(session):
                    for host in hosts:
                        if _flatten_host_per_reporter_staleness(host, logger, dry_run):
                            batch_hosts_updated += 1

                    last_host_id = hosts[-1].id
                    session.flush()

                org_hosts_processed += len(hosts)
                org_hosts_updated += batch_hosts_updated

                logger.info(
                    f"Org {org_id}: Processed batch of {len(hosts)} hosts, "
                    f"updated {batch_hosts_updated} hosts "
                    f"(total for org: {org_hosts_processed}/{org_hosts_updated})"
                )

            logger.info(
                f"Org {org_id} complete: {org_hosts_processed} hosts processed, {org_hosts_updated} hosts updated"
            )

            total_orgs_processed += 1
            total_hosts_processed += org_hosts_processed
            total_hosts_updated += org_hosts_updated

        logger.info(
            f"Job completed. Organizations processed: {total_orgs_processed}, "
            f"total hosts processed: {total_hosts_processed}, "
            f"total hosts updated: {total_hosts_updated}"
        )

        if dry_run:
            logger.info("This was a dry run - no actual changes were made to the database.")


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)
    job_type = "Flatten per-reporter staleness"
    sys.excepthook = partial(excepthook, logger, job_type)

    config, session, _, _, _, application = job_setup((), PROMETHEUS_JOB)

    try:
        run(config, logger, session, application)
    except Exception as e:
        logger.exception(f"Job failed: {e}")
        sys.exit(1)
    finally:
        session.close()

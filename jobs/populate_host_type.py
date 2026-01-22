#!/usr/bin/env python3

"""
Job to populate the host_type column for hosts where it is NULL.

This job finds all hosts that have host_type = NULL and populates them
using the _derive_host_type() logic based on system profile data.

The host_type is derived as follows:
- "edge" or "cluster": if explicitly set in system_profile
- "bootc": if bootc_status["booted"]["image_digest"] exists
- "conventional": default for traditional systems

Usage:
    python jobs/populate_host_type.py

Environment variables:
    DRY_RUN=true - Run in dry-run mode (default: true)
    SUSPEND_JOB=true - Suspend the job without running (default: true)
    POPULATE_HOST_TYPE_BATCH_SIZE=500 - Number of hosts to process per batch (default: 500)
"""

import os
import sys
from functools import partial
from logging import Logger

from connexion import FlaskApp
from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload

from app import create_app
from app.config import Config
from app.environment import RuntimeEnvironment
from app.logging import get_logger
from app.logging import threadctx
from app.models import Host
from jobs.common import excepthook
from jobs.common import job_setup
from lib.db import session_guard

PROMETHEUS_JOB = "inventory-populate-host-type"
LOGGER_NAME = "populate_host_type"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB
BATCH_SIZE = int(os.getenv("POPULATE_HOST_TYPE_BATCH_SIZE", 500))
SUSPEND_JOB = os.environ.get("SUSPEND_JOB", "true").lower() == "true"

application = create_app(RUNTIME_ENVIRONMENT)
app = application.app


def _count_hosts_with_null_host_type(session: Session) -> int:
    """
    Count hosts that have host_type = NULL.

    Args:
        session: Database session

    Returns:
        Total number of hosts with NULL host_type
    """
    return session.query(Host).filter(Host.host_type.is_(None)).count()


def _get_hosts_with_null_host_type(session: Session, chunk_size: int, last_host_id: str | None = None) -> list[Host]:
    """
    Query for hosts that have host_type = NULL.

    Args:
        session: Database session
        chunk_size: Number of hosts to return
        last_host_id: ID of the last processed host for pagination

    Returns:
        List of Host objects with NULL host_type
    """
    query = session.query(Host).options(joinedload(Host.static_system_profile)).filter(Host.host_type.is_(None))

    if last_host_id:
        query = query.filter(Host.id > last_host_id)

    return query.order_by(Host.id).limit(chunk_size).all()


def _update_host_type(host: Host, logger: Logger, dry_run: bool = False) -> bool:
    """
    Update the host_type column for a single host using _derive_host_type().

    Args:
        host: Host object to update
        logger: Logger instance
        dry_run: If True, only log what would be updated

    Returns:
        True if the host was updated, False otherwise
    """
    try:
        derived_type = host._derive_host_type()

        if dry_run:
            logger.info(f"[DRY RUN] Would update Host {host.id} host_type to '{derived_type}'")
            return True

        host.host_type = derived_type
        logger.debug(f"Updated Host {host.id} host_type to '{derived_type}'")
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
    chunk_size = BATCH_SIZE

    if dry_run:
        logger.info(f"Running {PROMETHEUS_JOB} in dry-run mode. No data will be modified.")
    else:
        logger.info(f"Running {PROMETHEUS_JOB} in update mode. Data WILL be modified.")

    with application.app.app_context():
        threadctx.request_id = None

        # In dry-run mode, just count and exit immediately
        if dry_run:
            total_hosts = _count_hosts_with_null_host_type(session)
            logger.info(f"Dry-run complete. Found {total_hosts} hosts with NULL host_type that would be updated.")
            logger.info("This was a dry run - no actual changes were made to the database.")
            return

        total_hosts_processed = 0
        total_hosts_updated = 0
        last_host_id = None

        while True:
            # Get the next batch of hosts
            hosts = _get_hosts_with_null_host_type(session, chunk_size, last_host_id)

            logger.info(f"Found {len(hosts)} hosts to process")

            if not hosts:
                logger.info("No more hosts to process")
                break

            batch_hosts_updated = 0

            with session_guard(session):
                for host in hosts:
                    if _update_host_type(host, logger, dry_run):
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
    job_type = "Populate host_type column"
    sys.excepthook = partial(excepthook, logger, job_type)

    if SUSPEND_JOB:
        logger.info("SUSPEND_JOB set to true; exiting.")
        sys.exit(0)

    config, session, _, _, _, application = job_setup((), PROMETHEUS_JOB)

    try:
        run(config, logger, session, application)
    except Exception as e:
        logger.exception(f"Job failed: {e}")
        sys.exit(1)
    finally:
        session.close()

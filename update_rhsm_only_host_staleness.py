#!/usr/bin/python
"""
Migration script to update existing hosts that have only "rhsm-conduit" as a reporter.
These hosts should stay fresh forever, so we need to update their staleness timestamps
to far-future values.
"""

import os
import sys
from datetime import datetime
from datetime import timezone
from functools import partial
from logging import Logger

from connexion import FlaskApp
from sqlalchemy import and_
from sqlalchemy import not_
from sqlalchemy.dialects.postgresql import array
from sqlalchemy.orm import Session

from app.environment import RuntimeEnvironment
from app.logging import get_logger
from app.models import Host
from app.models.constants import EDGE_HOST_STALE_TIMESTAMP
from app.models.host import should_host_stay_fresh_forever
from jobs.common import excepthook
from jobs.common import job_setup

PROMETHEUS_JOB = "inventory-update-rhsm-conduit-only-hosts-staleness"
LOGGER_NAME = "update-rhsm-conduit-only-hosts-staleness"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB

# Process hosts in batches to avoid overwhelming the database
BATCH_SIZE = int(os.getenv("HOST_UPDATE_BATCH_SIZE", 1000))


def find_rhsm_conduit_only_hosts(session: Session, logger: Logger):
    """
    Find hosts that have only "rhsm-conduit" as a reporter.
    These are hosts where per_reporter_staleness contains only "rhsm-conduit" and no other reporters.
    """
    logger.info("Finding hosts with only 'rhsm-conduit' as a reporter...")

    # Find hosts that:
    # 1. Have "rhsm-conduit" in per_reporter_staleness
    # 2. Don't have any of the other common reporters
    other_reporters = ["cloud-connector", "puptoo", "rhsm-system-profile-bridge", "yuptoo", "discovery", "satellite"]

    query_filter = and_(
        Host.per_reporter_staleness.has_key("rhsm-conduit"),
        not_(Host.per_reporter_staleness.has_any(array(other_reporters))),
    )

    hosts_query = session.query(Host).filter(query_filter)
    total_count = hosts_query.count()

    logger.info(f"Found {total_count} hosts with only 'rhsm-conduit' as a reporter")
    return hosts_query, total_count


def update_host_staleness_timestamps(host: Host, logger: Logger):
    """
    Update a host's staleness timestamps to far-future values.
    """
    far_future = EDGE_HOST_STALE_TIMESTAMP

    # Update main staleness timestamps
    host.stale_timestamp = far_future
    host.stale_warning_timestamp = far_future
    host.deletion_timestamp = far_future

    # Update per_reporter_staleness for rhsm-conduit
    if host.per_reporter_staleness and "rhsm-conduit" in host.per_reporter_staleness:
        # Preserve the existing last_check_in timestamp
        existing_last_check_in = host.per_reporter_staleness["rhsm-conduit"].get("last_check_in") or (
            host.last_check_in.isoformat() if host.last_check_in else datetime.now(timezone.utc).isoformat()
        )

        host.per_reporter_staleness["rhsm-conduit"].update(
            {
                "stale_timestamp": far_future.isoformat(),
                "stale_warning_timestamp": far_future.isoformat(),
                "culled_timestamp": far_future.isoformat(),
                "last_check_in": existing_last_check_in,
                "check_in_succeeded": True,
            }
        )

        # Mark the field as modified for SQLAlchemy
        from sqlalchemy import orm

        orm.attributes.flag_modified(host, "per_reporter_staleness")

    logger.debug(f"Updated staleness timestamps for host {host.id} to far-future values")


def run(logger: Logger, session: Session, application: FlaskApp):
    """
    Main function to update existing rhsm-conduit-only hosts.
    """
    with application.app.app_context():
        logger.info("Starting migration to update rhsm-conduit-only hosts staleness timestamps")

        # Find all hosts that need to be updated
        hosts_query, total_count = find_rhsm_conduit_only_hosts(session, logger)

        if total_count == 0:
            logger.info("No hosts found that need updating. Migration complete.")
            return

        # Process hosts in batches
        processed_count = 0
        updated_count = 0

        logger.info(f"Processing {total_count} hosts in batches of {BATCH_SIZE}")

        for host in hosts_query.yield_per(BATCH_SIZE):
            try:
                # Double-check that this host should stay fresh forever
                if should_host_stay_fresh_forever(host):
                    # Check if the host already has far-future timestamps
                    far_future = EDGE_HOST_STALE_TIMESTAMP
                    needs_update = (
                        host.stale_timestamp != far_future
                        or host.stale_warning_timestamp != far_future
                        or host.deletion_timestamp != far_future
                    )

                    if needs_update:
                        update_host_staleness_timestamps(host, logger)
                        updated_count += 1

                        # Commit every BATCH_SIZE updates to avoid large transactions
                        if updated_count % BATCH_SIZE == 0:
                            session.commit()
                            logger.info(f"Updated {updated_count}/{total_count} hosts...")
                    else:
                        logger.debug(f"Host {host.id} already has correct timestamps, skipping")
                else:
                    logger.warning(f"Host {host.id} was found by query but doesn't match stay-fresh criteria")

                processed_count += 1

            except Exception as e:
                logger.error(f"Error updating host {host.id}: {e}")
                # Continue processing other hosts even if one fails
                continue

        # Final commit for any remaining updates
        if updated_count % BATCH_SIZE != 0:
            session.commit()

        logger.info(f"Migration complete. Processed {processed_count} hosts, updated {updated_count} hosts.")
        logger.info("Hosts with only 'rhsm-conduit' reporter will now stay fresh forever.")


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)
    job_type = "Update rhsm-conduit-only hosts staleness"
    sys.excepthook = partial(excepthook, logger, job_type)

    _, session, _, _, _, application = job_setup((), PROMETHEUS_JOB)
    run(logger, session, application)

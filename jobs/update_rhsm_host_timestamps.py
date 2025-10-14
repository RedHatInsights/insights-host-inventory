#!/usr/bin/python3

# mypy: disallow-untyped-defs

import sys
from functools import partial
from logging import Logger

from connexion import FlaskApp
from sqlalchemy import func
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import Config
from app.environment import RuntimeEnvironment
from app.logging import get_logger
from app.logging import threadctx
from app.models import Host
from app.models.constants import FAR_FUTURE_STALE_TIMESTAMP
from jobs.common import excepthook
from jobs.common import job_setup
from lib.db import session_guard

PROMETHEUS_JOB = "inventory-update-rhsm-host-timestamps"
LOGGER_NAME = "update_rhsm_host_timestamps"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB


def run(config: Config, logger: Logger, session: Session, application: FlaskApp) -> None:
    if config.dry_run:
        logger.info(f"Running {PROMETHEUS_JOB} in dry-run mode. Host timestamps will NOT be updated.")
    else:
        logger.info(f"Running {PROMETHEUS_JOB} without dry-run. Host timestamps WILL be updated.")

    with application.app.app_context():
        threadctx.request_id = None

        # Count total hosts to update
        query = session.query(Host).filter(
            # Filter for RHSM-only hosts
            Host.per_reporter_staleness
            == func.jsonb_build_object(
                "rhsm-system-profile-bridge", Host.per_reporter_staleness["rhsm-system-profile-bridge"]
            ),
            # Filter for hosts where any of the timestamps is not FAR_FUTURE_STALE_TIMESTAMP
            or_(
                Host.stale_timestamp != FAR_FUTURE_STALE_TIMESTAMP,
                Host.stale_warning_timestamp != FAR_FUTURE_STALE_TIMESTAMP,
                Host.deletion_timestamp != FAR_FUTURE_STALE_TIMESTAMP,
            ),
        )

        total_hosts = query.count()
        logger.info(f"Found {total_hosts} RHSM-only hosts with incorrect timestamps")

        if total_hosts == 0 or config.dry_run:
            logger.info("No hosts to update or running in dry-run mode. Exiting.")
            session.close()
            return

        hosts_processed = 0
        hosts = query.order_by(Host.id).limit(config.script_chunk_size).all()

        while len(hosts) > 0:
            last_host_id = hosts[-1].id  # Save ID before session_guard context
            with session_guard(session):
                for host in hosts:
                    host._update_staleness_timestamps()
                    host._update_per_reporter_staleness("rhsm-system-profile-bridge")

            hosts_processed += len(hosts)
            logger.info(f"Updated {len(hosts)} hosts (total: {hosts_processed}/{total_hosts})")

            hosts = query.filter(Host.id > last_host_id).order_by(Host.id).limit(config.script_chunk_size).all()

        logger.info(f"Done updating RHSM host timestamps. Total hosts updated: {hosts_processed}")
        session.close()


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)
    job_type = "Update RHSM host timestamps"
    sys.excepthook = partial(excepthook, logger, job_type)

    config, session, _, _, _, application = job_setup((), PROMETHEUS_JOB)
    try:
        run(config, logger, session, application)
    except Exception as e:
        logger.exception(e)
    finally:
        session.close()

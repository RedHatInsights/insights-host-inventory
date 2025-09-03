#!/usr/bin/python3
import sys
from functools import partial
from logging import Logger

from connexion import FlaskApp
from sqlalchemy.orm import Session

from app.environment import RuntimeEnvironment
from app.logging import get_logger
from app.models import Host
from app.models import Staleness
from jobs.common import excepthook
from jobs.common import job_setup

PROMETHEUS_JOB = "inventory-update-edge-staleness-timestamps"
LOGGER_NAME = "update-edge-hosts-staleness-timestamps"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB


def run(logger: Logger, session: Session, application: FlaskApp):
    with application.app.app_context():
        logger.info("Starting edge hosts staleness timestamps update job")

        # Get all edge hosts
        edge_hosts = session.query(Host).filter(Host.host_type == "edge").all()

        logger.info(f"Found {len(edge_hosts)} edge hosts to update staleness timestamps")

        for host in edge_hosts:
            # Lookup staleness config for this host
            staleness_config = session.query(Staleness).filter(Staleness.org_id == host.org_id)

            # TODO: Update timestamps based on config
            # host.stale_timestamp =
            # host.stale_warning_timestamp =
            # host.deletion_timestamp =

            logger.debug(
                f"Updated host {host.id} stale_timestamp={host.stale_timestamp}, "
                f"stale_warning_timestamp={host.stale_warning_timestamp}, "
                f"deletion_timestamp={host.deletion_timestamp}, "
            )

        if edge_hosts:
            session.commit()
            logger.info(f"Updated {len(edge_hosts)} edge hosts staleness timestamps fields")


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)
    job_type = "Update edge hosts staleness timestamps"
    sys.excepthook = partial(excepthook, logger, job_type)

    _, session, _, _, _, application = job_setup((), PROMETHEUS_JOB)
    run(logger, session, application)

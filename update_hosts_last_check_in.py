#!/usr/bin/python
import os
import sys
from functools import partial
from logging import Logger

from connexion import FlaskApp
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.environment import RuntimeEnvironment
from app.logging import get_logger
from app.models import Host
from jobs.common import excepthook
from jobs.common import job_setup

PROMETHEUS_JOB = "inventory-update-hosts-last-check-in"
LOGGER_NAME = "update-hosts-last-check-in"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB

LIMIT = int(os.getenv("HOST_UPDATE_LIMIT", 50000))


def run(logger: Logger, session: Session, application: FlaskApp):
    with application.app.app_context():
        logger.info("Starting update host last_check_in field job")
        num_hosts_null_last_check_in = session.query(Host).filter(Host.last_check_in.is_(None)).count()

        if num_hosts_null_last_check_in > 0:
            logger.info(f"There are still {num_hosts_null_last_check_in} to be updated")
            logger.info(f"Updating {LIMIT} hosts' last_check_in field")
            session.execute(
                text(
                    "UPDATE hbi.hosts h SET last_check_in  = modified_on "
                    f"WHERE h.id IN (SELECT id FROM hbi.hosts sub WHERE sub.last_check_in is NULL LIMIT {LIMIT});"
                )
            )
            session.commit()


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)
    job_type = "Update host last_check_in field"
    sys.excepthook = partial(excepthook, logger, job_type)

    _, session, event_producer, _, _, application = job_setup(tuple(), PROMETHEUS_JOB)
    run(logger, session, application)

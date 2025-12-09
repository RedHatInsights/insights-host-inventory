#!/usr/bin/python3
import sys
from functools import partial
from logging import Logger

from connexion import FlaskApp
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.environment import RuntimeEnvironment
from app.logging import get_logger
from jobs.common import excepthook
from jobs.common import job_setup

PROMETHEUS_JOB = "inventory-add-inventory-view"
LOGGER_NAME = "add-inventory-view"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB


def run(logger: Logger, session: Session, application: FlaskApp):
    with application.app.app_context():
        logger.info("Starting add inventory view job")
        CREATE_SCHEMA_SQL = "CREATE SCHEMA IF NOT EXISTS inventory"
        CREATE_VIEW_SQL = """
            CREATE OR REPLACE VIEW inventory.hosts AS SELECT
                    id,
                    account,
                    display_name,
                    created_on as created,
                    modified_on as updated,
                    stale_timestamp,
                    stale_warning_timestamp,
                    deletion_timestamp AS culled_timestamp,
                    tags_alt as tags,
                    system_profile_facts as system_profile,
                    insights_id,
                    reporter,
                    per_reporter_staleness,
                    org_id,
                    groups
                FROM hbi.hosts WHERE insights_id IS NOT NULL;
        """
        session.execute(text(CREATE_SCHEMA_SQL))
        session.execute(text(CREATE_VIEW_SQL))
        session.commit()


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)
    job_type = "Add inventory view"
    sys.excepthook = partial(excepthook, logger, job_type)

    _, session, event_producer, _, _, application = job_setup(tuple(), PROMETHEUS_JOB)
    run(logger, session, application)

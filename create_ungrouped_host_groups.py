#!/usr/bin/python
import sys
from functools import partial
from logging import Logger

from connexion import FlaskApp
from sqlalchemy.orm import Session

from app.environment import RuntimeEnvironment
from app.logging import get_logger
from app.logging import threadctx
from app.models import Group
from app.models import Host
from jobs.common import excepthook
from jobs.common import job_setup
from lib.db import session_guard
from lib.group_repository import add_group

PROMETHEUS_JOB = "inventory-create-ungrouped-groups"
LOGGER_NAME = "create_ungrouped_groups"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB


def run(logger: Logger, session: Session, application: FlaskApp):
    with application.app.app_context():
        threadctx.request_id = None
        # For each org_id in the Hosts table
        # Using "org_id," (with comma) because the query returns tuples
        with session_guard(session):
            for org_id, account in session.query(Host.org_id, Host.account).distinct():
                logger.info(f"Processing org_id: {org_id}")

                # Check to see if this org already has an "ungrouped hosts" group
                ungrouped_group = (
                    session.query(Group).filter(Group.org_id == org_id, Group.ungrouped.is_(True)).one_or_none()
                )

                # If not, create the "ungrouped hosts" Group
                if ungrouped_group is None:
                    ungrouped_group = add_group(
                        group_name="Ungrouped Hosts", org_id=org_id, account=account, ungrouped=True
                    )
                    logger.info(f"Created group {ungrouped_group.id} for org_id {org_id}")
                else:
                    logger.debug(f"org_id {org_id} already has an ungrouped Group: {ungrouped_group.id}")

        logger.info("Finished creating 'Ungrouped Hosts' Groups. Exiting.")


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)
    job_type = "Create ungrouped host groups"
    sys.excepthook = partial(excepthook, logger, job_type)

    _, session, _, _, _, application = job_setup((), PROMETHEUS_JOB)
    run(logger, session, application)

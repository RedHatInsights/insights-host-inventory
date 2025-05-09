#!/usr/bin/python
import os
import sys
from functools import partial
from logging import Logger

from connexion import FlaskApp
from sqlalchemy.orm import Session

from app.auth.identity import create_mock_identity_with_org_id
from app.environment import RuntimeEnvironment
from app.logging import get_logger
from app.logging import threadctx
from app.models import Group
from app.queue.event_producer import EventProducer
from jobs.common import excepthook
from jobs.common import job_setup
from lib.db import session_guard
from lib.group_repository import delete_group_list

PROMETHEUS_JOB = "inventory-delete-ungrouped-groups"
LOGGER_NAME = "delete_ungrouped_groups"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB
BATCH_SIZE = int(os.getenv("DELETE_UNGROUPED_GROUPS_BATCH_SIZE", 50))


def run(logger: Logger, session: Session, event_producer: EventProducer, application: FlaskApp):
    with application.app.app_context(), session_guard(session):
        threadctx.request_id = None

        # Grab the first 50 ungrouped groups.
        # We don't need offset() because the loop deletes the groups.
        for group in session.query(Group).filter(Group.ungrouped.is_(True)).limit(BATCH_SIZE).all():
            logger.debug(f"Deleting group with id {group.id} and org_id {group.org_id}.")
            delete_group_list([str(group.id)], create_mock_identity_with_org_id(group.org_id), event_producer)

        logger.info("Finished deleting 'Ungrouped Hosts' groups.")


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)
    job_type = "Delete ungrouped host groups"
    sys.excepthook = partial(excepthook, logger, job_type)

    _, session, event_producer, _, _, application = job_setup((), PROMETHEUS_JOB)
    run(logger, session, event_producer, application)

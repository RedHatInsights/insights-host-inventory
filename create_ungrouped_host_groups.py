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
from app.models import Host
from app.queue.event_producer import EventProducer
from jobs.common import excepthook
from jobs.common import job_setup
from lib.group_repository import add_group
from lib.group_repository import add_hosts_to_group

PROMETHEUS_JOB = "inventory-create-ungrouped-groups"
LOGGER_NAME = "create_ungrouped_groups"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB
BATCH_SIZE = int(os.getenv("CREATE_UNGROUPED_GROUPS_BATCH_SIZE", 50))


def run(logger: Logger, session: Session, event_producer: EventProducer, application: FlaskApp):
    with application.app.app_context():
        threadctx.request_id = None
        # For each org_id in the Hosts table
        # Using "org_id," (with comma) because the query returns tuples
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

            # Store the ID so it persists after commit
            ungrouped_group_id = ungrouped_group.id

            # Assign all ungrouped hosts to this new Group in batches of 50
            while True:
                # Grab the first 50 ungrouped hosts in the org.
                # We don't need offset() because Host.groups is populated during add_hosts_to_group().
                host_ids = (
                    session.query(Host.id).filter(Host.org_id == org_id, Host.groups == []).limit(BATCH_SIZE).all()
                )
                if not host_ids:
                    break
                # host_ids is a list of tuples, so extract the ids
                host_id_list = [str(host_id) for (host_id,) in host_ids]
                add_hosts_to_group(
                    ungrouped_group_id, host_id_list, create_mock_identity_with_org_id(org_id), event_producer
                )


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)
    job_type = "Create ungrouped host groups"
    sys.excepthook = partial(excepthook, logger, job_type)

    _, session, event_producer, _, _, application = job_setup((), PROMETHEUS_JOB)
    run(logger, session, event_producer, application)

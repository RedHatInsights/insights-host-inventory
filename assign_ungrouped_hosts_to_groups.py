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
from app.models import HostGroupAssoc
from app.queue.event_producer import EventProducer
from jobs.common import excepthook
from jobs.common import job_setup
from lib.group_repository import add_hosts_to_group

PROMETHEUS_JOB = "inventory-assign-ungrouped-groups"
LOGGER_NAME = "assign_ungrouped_groups"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB
BATCH_SIZE = int(os.getenv("ASSIGN_UNGROUPED_GROUPS_BATCH_SIZE", 25))


def run(logger: Logger, session: Session, event_producer: EventProducer, application: FlaskApp):
    with application.app.app_context():
        threadctx.request_id = None
        # For each org_id in the Hosts table
        # Using "org_id," (with comma) because the query returns tuples
        org_id_list = [org_id for (org_id,) in session.query(Host.org_id).distinct()]
        for org_id in org_id_list:
            logger.info(f"Processing org_id: {org_id}")

            # Find the org's "ungrouped" group and store its ID
            ungrouped_group = (
                session.query(Group).filter(Group.org_id == org_id, Group.ungrouped.is_(True)).one_or_none()
            )
            if not ungrouped_group:
                logger.warning(f"No ungrouped group found for org_id: {org_id}")
                continue
            ungrouped_group_id = ungrouped_group.id

            # Assign all ungrouped hosts to this new Group in batches
            while True:
                # Grab the first batch of ungrouped hosts in the org.
                # We don't need offset() because Host are assigned to Groups in add_hosts_to_group().
                host_ids = (
                    session.query(Host.id)
                    .outerjoin(HostGroupAssoc, Host.id == HostGroupAssoc.host_id)
                    .filter(Host.org_id == org_id, HostGroupAssoc.host_id.is_(None))
                    .limit(BATCH_SIZE)
                    .all()
                )
                if host_id_list := [str(host_id) for (host_id,) in host_ids]:
                    add_hosts_to_group(
                        ungrouped_group_id,
                        host_id_list,
                        create_mock_identity_with_org_id(org_id),
                        event_producer,
                        session,
                    )
                else:
                    break

            session.expunge_all()


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)
    job_type = "Assign ungrouped hosts to ungrouped groups"
    sys.excepthook = partial(excepthook, logger, job_type)

    config, session, event_producer, _, _, application = job_setup((), PROMETHEUS_JOB)
    if config.bypass_kessel_jobs:
        logger.info("bypass_kessel_jobs was set to True; exiting.")
        sys.exit(0)
    else:
        run(logger, session, event_producer, application)

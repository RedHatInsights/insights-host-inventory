#!/usr/bin/python3
import os
import sys
from functools import partial
from logging import Logger

from connexion import FlaskApp
from sqlalchemy.orm import Session

from app.common import inventory_config
from app.environment import RuntimeEnvironment
from app.logging import get_logger
from app.logging import threadctx
from app.models import Group
from app.models import Host
from app.models import HostGroupAssoc
from jobs.common import excepthook
from jobs.common import job_setup
from lib.db import session_guard

PROMETHEUS_JOB = "inventory-assign-ungrouped-groups"
LOGGER_NAME = "assign_ungrouped_groups"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB
BATCH_SIZE = int(os.getenv("ASSIGN_UNGROUPED_GROUPS_BATCH_SIZE", 25))


def run(logger: Logger, session: Session, application: FlaskApp):
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
            hosts_to_process = 1
            while hosts_to_process > 0:
                # Grab the first batch of ungrouped hosts in the org.
                # We don't need offset() because Host are assigned to Groups in add_hosts_to_group().
                with session_guard(session):
                    host_ids = (
                        session.query(Host.id)
                        .outerjoin(HostGroupAssoc, Host.id == HostGroupAssoc.host_id)
                        .filter(Host.org_id == org_id, HostGroupAssoc.host_id.is_(None))
                        .order_by(Host.id)
                        .limit(BATCH_SIZE)
                        .all()
                    )
                    hosts_to_process = len(host_ids)
                    for (host_id,) in host_ids:
                        if inventory_config().hbi_db_refactoring_use_old_table:
                            # Old code: constructor without org_id
                            assoc = HostGroupAssoc(host_id, ungrouped_group_id)
                        else:
                            # New code: constructor with org_id
                            assoc = HostGroupAssoc(host_id, ungrouped_group_id, org_id)
                        session.add(assoc)
                    logger.info(f"Created {len(host_ids)} host-group associations for org {org_id}.")


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)
    job_type = "Assign ungrouped hosts to ungrouped groups"
    sys.excepthook = partial(excepthook, logger, job_type)

    config, session, _, _, _, application = job_setup((), PROMETHEUS_JOB)
    if config.bypass_kessel_jobs:
        logger.info("bypass_kessel_jobs was set to True; exiting.")
        sys.exit(0)
    else:
        run(logger, session, application)

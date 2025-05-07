#!/usr/bin/python
import os
import sys
from functools import partial
from logging import Logger

import sqlalchemy as sa
from connexion import FlaskApp
from sqlalchemy import and_
from sqlalchemy import or_
from sqlalchemy import orm
from sqlalchemy.engine.base import Connection
from sqlalchemy.orm import Mapper
from sqlalchemy.orm import Session

from app.environment import RuntimeEnvironment
from app.logging import get_logger
from app.models import Host
from jobs.common import excepthook
from jobs.common import job_setup

PROMETHEUS_JOB = "inventory-update-edge-hosts-prs"
LOGGER_NAME = "update-edge-hosts-prs"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB

UPDATE_EDGE_HOSTS_STALENESS = int(os.getenv("UPDATE_EDGE_HOSTS_STALENESS", 100))


@sa.event.listens_for(Host, "before_update")
def receive_before_host_update(mapper: Mapper, connection: Connection, host: Host):  # noqa: ARG001
    """Prevent host modified_on update during staleness updates.

    This SQLAlchemy event listener, triggered before any host update,
    prevents the ``modified_on`` timestamp from being updated when only
    the ``per_reporter_staleness`` field is changed.  This avoids
    unnecessary updates as ``modified_on`` is automatically updated for
    every change to a Host object, which can lead to confusion to the user.

    For more details on SQLAlchemy event listeners, see:
    https://docs.sqlalchemy.org/en/20/orm/events.html#sqlalchemy.orm.MapperEvents.before_update

    :param mapper: The SQLAlchemy mapper.
    :param connection: The database connection.
    :param host: The Host object being updated.
    """
    host_details = sa.inspect(host)
    flag_changed, _, _ = host_details.attrs.per_reporter_staleness.history
    if flag_changed:
        orm.attributes.flag_modified(host, "modified_on")


def run(logger: Logger, session: Session, application: FlaskApp):
    with application.app.app_context():
        logger.info("Starting job to update per_reporter_staleness field")

        # We only want to update Edge hosts, as other hosts are going to update
        # this value during host check in.
        reporters_list = [
            "cloud-connector",
            "puptoo",
            "rhsm-conduit",
            "rhsm-system-profile-bridge",
            "yuptoo",
            "discovery",
            "satellite",
        ]
        query_filter = and_(
            Host.system_profile_facts.has_key("host_type"),
            or_(~Host.per_reporter_staleness[reporter].has_key("culled_timestamp") for reporter in reporters_list),
        )
        query = session.query(Host).filter(query_filter)
        num_edge_hosts = query.count()

        if num_edge_hosts > 0:
            logger.info(f"There are still {num_edge_hosts} to be updated")
            for host in query.order_by(Host.org_id).yield_per(UPDATE_EDGE_HOSTS_STALENESS):
                host._update_all_per_reporter_staleness()
                host._update_staleness_timestamps()
            session.commit()


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)
    job_type = "Update host per_reporter_staleness field for edge hosts"
    sys.excepthook = partial(excepthook, logger, job_type)

    _, session, event_producer, _, _, application = job_setup(tuple(), PROMETHEUS_JOB)
    session.expire_on_commit = False
    run(logger, session, application)

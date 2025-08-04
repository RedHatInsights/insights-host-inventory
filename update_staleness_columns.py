#!/usr/bin/python
import os
import sys
from functools import partial
from logging import Logger

import sqlalchemy as sa
from connexion import FlaskApp
from sqlalchemy import or_
from sqlalchemy import orm
from sqlalchemy.engine.base import Connection
from sqlalchemy.orm import Mapper
from sqlalchemy.orm import Session

from api.staleness_query import get_staleness_obj
from app.common import inventory_config
from app.culling import Timestamps
from app.environment import RuntimeEnvironment
from app.logging import get_logger
from app.models import Host
from jobs.common import excepthook
from jobs.common import job_setup

PROMETHEUS_JOB = "inventory-update-staleness-columns"
LOGGER_NAME = "update-staleness-columns"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB

NUM_HOSTS_UPDATE_STALENESS = int(os.getenv("NUM_HOSTS_UPDATE_STALENESS", 500))


@sa.event.listens_for(Host, "before_update")
def receive_before_host_update(mapper: Mapper, connection: Connection, host: Host):  # noqa: ARG001
    """Prevent host modified_on update during staleness updates.

    This SQLAlchemy event listener, triggered before any host update,
    prevents the ``modified_on`` timestamp from being updated when only
    the ``per_reporter_staleness`` field or host-level staleness fields are changed.
    This avoids unnecessary updates as ``modified_on`` is automatically updated for
    every change to a Host object, which can lead to confusion to the user.

    For more details on SQLAlchemy event listeners, see:
    https://docs.sqlalchemy.org/en/20/orm/events.html#sqlalchemy.orm.MapperEvents.before_update

    :param mapper: The SQLAlchemy mapper.
    :param connection: The database connection.
    :param host: The Host object being updated.
    """
    host_details = sa.inspect(host)
    prs_changed, _, _ = host_details.attrs.per_reporter_staleness.history
    staleness_changed, _, _ = host_details.attrs.deletion_timestamp.history
    if prs_changed or staleness_changed:
        orm.attributes.flag_modified(host, "modified_on")


def run(logger: Logger, session: Session, application: FlaskApp):
    with application.app.app_context():
        logger.info("Starting job to update staleness columns and per_reporter_staleness field")

        reporters_list = [
            "cloud-connector",
            "puptoo",
            "rhsm-conduit",
            "rhsm-system-profile-bridge",
            "yuptoo",
            "discovery",
            "satellite",
        ]
        query_filter = or_(
            or_(~Host.per_reporter_staleness[reporter].has_key("culled_timestamp") for reporter in reporters_list),
            or_(
                ~Host.per_reporter_staleness[reporter].has_key("stale_warning_timestamp")
                for reporter in reporters_list
            ),
            or_(Host.stale_warning_timestamp.is_(None), Host.deletion_timestamp.is_(None)),
        )

        hosts_query = session.query(Host).filter(query_filter).order_by(Host.org_id)
        hosts_count = hosts_query.count()

        logger.info(f"Found {hosts_count} to be updated")
        processed_in_current_batch = 0
        total_hosts_updated = 0

        org_id = None
        for host in hosts_query.yield_per(NUM_HOSTS_UPDATE_STALENESS):
            try:
                if org_id is None or org_id != host.org_id:
                    org_id = host.org_id
                    staleness = get_staleness_obj(org_id)
                    staleness_ts = Timestamps.from_config(inventory_config())

                host._update_all_per_reporter_staleness(staleness, staleness_ts)
                host._update_staleness_timestamps()

                processed_in_current_batch += 1
                total_hosts_updated += 1
                if processed_in_current_batch >= NUM_HOSTS_UPDATE_STALENESS:
                    logger.info(f"Updating batch of {processed_in_current_batch} hosts...")
                    session.flush()  # Flush current session so we free memory
                    session.commit()
                    logger.info(f"Flushed and commited. Total updated so far: {total_hosts_updated}")
                    processed_in_current_batch = 0  # Reset counter for the next batch

            except Exception as e:
                logger.error(f"Error committing batch: {e}", exc_info=True)
                session.rollback()

            logger.info(f"Job finished. Successfully updated staleness for {total_hosts_updated} hosts.")
        else:
            logger.info("No hosts to be updated. Finishing job")


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)
    job_type = "Update hosts' staleness columns and per_reporter_staleness field"
    sys.excepthook = partial(excepthook, logger, job_type)

    _, session, event_producer, _, _, application = job_setup(tuple(), PROMETHEUS_JOB)
    session.expire_on_commit = False
    run(logger, session, application)

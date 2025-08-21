#!/usr/bin/python3
import os
import sys
from functools import partial
from logging import Logger

from connexion import FlaskApp
from sqlalchemy.orm import Session

from app.environment import RuntimeEnvironment
from app.logging import get_logger
from app.models import Host
from jobs.common import excepthook
from jobs.common import job_setup
from lib.db import session_guard

PROMETHEUS_JOB = "inventory-delete-host-namespace-access-tags"
LOGGER_NAME = "delete-host-namespace-access-tags"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB
NUM_HOSTS_TAG_DELETION_BATCH_COUNT = int(os.getenv("NUM_HOSTS_TAG_DELETION_BATCH_COUNT", 500))
TAG_ACCESS_NAMESPACE = os.getenv("TAG_ACCESS_NAMESPACE", "sat_iam")


def run(logger: Logger, session: Session, application: FlaskApp):
    with application.app.app_context():
        logger.info("Starting job to delete access tags on hosts")
        hosts_query = session.query(Host).filter(Host.tags.has_key(TAG_ACCESS_NAMESPACE)).order_by(Host.org_id)
        hosts_count = hosts_query.count()
        logger.info(f"Found {hosts_count} to be updated")
        processed_in_current_batch = 0
        total_hosts_updated = 0

        for host in hosts_query.yield_per(NUM_HOSTS_TAG_DELETION_BATCH_COUNT):
            try:
                if host.tags is not None and TAG_ACCESS_NAMESPACE in host.tags:
                    host._delete_tags_namespace(TAG_ACCESS_NAMESPACE)
                    host._delete_tags_alt_namespace(TAG_ACCESS_NAMESPACE)
                processed_in_current_batch += 1
                total_hosts_updated += 1
                if processed_in_current_batch >= NUM_HOSTS_TAG_DELETION_BATCH_COUNT:
                    logger.info(f"Updating batch of {processed_in_current_batch} hosts...")
                    session.flush()  # Flush current session so we free memory
                    logger.info(f"Flushed. Total updated so far: {total_hosts_updated}")
                    processed_in_current_batch = 0  # Reset counter for the next batch

            except Exception as e:
                logger.error(f"Error committing batch: {e}", exc_info=True)
                session.rollback()

        if total_hosts_updated > 0:
            try:
                logger.info(f"Committing {total_hosts_updated} hosts.")
                session.commit()
                logger.info(f"Job finished. Successfully deleted access tags for {total_hosts_updated} hosts.")
            except Exception:
                session.rollback()
        else:
            logger.info("No hosts to be updated. Finishing job")


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)
    job_type = "Delete host access tags hosts"
    sys.excepthook = partial(excepthook, logger, job_type)

    _, session, event_producer, _, _, application = job_setup(tuple(), PROMETHEUS_JOB)
    session.expire_on_commit = False
    with session_guard(session):
        run(logger, session, application)

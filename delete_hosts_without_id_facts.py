#!/usr/bin/python

import sys
from functools import partial
from logging import Logger

from connexion import FlaskApp
from sqlalchemy.dialects.postgresql import array
from sqlalchemy.orm import Session

from app.config import Config
from app.environment import RuntimeEnvironment
from app.logging import get_logger
from app.logging import threadctx
from app.models import Host
from app.queue.event_producer import EventProducer
from jobs.common import excepthook
from jobs.common import job_setup
from lib.handlers import ShutdownHandler
from lib.host_delete import delete_hosts

PROMETHEUS_JOB = "inventory-delete-hosts-without-id-facts"
LOGGER_NAME = "delete_hosts_without_id_facts"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB


def run(
    config: Config,
    logger: Logger,
    session: Session,
    event_producer: EventProducer,
    notifications_event_producer: EventProducer,
    shutdown_handler: ShutdownHandler,
    application: FlaskApp,
) -> None:
    with application.app.app_context():
        threadctx.request_id = None
        query = session.query(Host).filter(
            ~Host.canonical_facts.has_any(array(["provider_id", "subscription_manager_id", "insights_id"]))
        )

        try:
            logger.info(f"Deleting {query.count()} hosts without ID facts")
            deleted_hosts_count = len(
                list(
                    delete_hosts(
                        query,
                        event_producer,
                        notifications_event_producer,
                        config.host_delete_chunk_size,
                        shutdown_handler.shut_down,
                    )
                )
            )
        except InterruptedError:
            logger.info(f"{PROMETHEUS_JOB} was interrupted.")
            deleted_hosts_count = 0

        logger.info(f"Finished deleting {deleted_hosts_count} hosts without ID facts.")


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)
    job_type = "Delete hosts without ID facts"
    sys.excepthook = partial(excepthook, logger, job_type)

    config, session, event_producer, notifications_event_producer, shutdown_handler, application = job_setup(
        (), PROMETHEUS_JOB
    )
    run(config, logger, session, event_producer, notifications_event_producer, shutdown_handler, application)

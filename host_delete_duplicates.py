from __future__ import annotations

import sys
from functools import partial
from logging import Logger

from connexion import FlaskApp
from sqlalchemy.orm import Session

from app.config import Config
from app.environment import RuntimeEnvironment
from app.logging import get_logger
from app.logging import threadctx
from app.queue.event_producer import EventProducer
from jobs.common import excepthook
from jobs.common import init_db
from jobs.common import job_setup
from lib.db import multi_session_guard
from lib.handlers import ShutdownHandler
from lib.handlers import register_shutdown
from lib.host_remove_duplicates import delete_duplicate_hosts
from lib.metrics import delete_duplicate_host_count

__all__ = ("run",)

PROMETHEUS_JOB = "duplicate-hosts-remover"
LOGGER_NAME = "duplicate-hosts-remover"
COLLECTED_METRICS = (delete_duplicate_host_count,)
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB


def run(
    config: Config,
    logger: Logger,
    org_ids_session: Session,
    hosts_session: Session,
    misc_session: Session,
    event_producer: EventProducer,
    notifications_event_producer: EventProducer,
    shutdown_handler: ShutdownHandler,
    application: FlaskApp,
) -> int | None:
    with application.app.app_context():
        threadctx.request_id = None
        try:
            num_deleted = delete_duplicate_hosts(
                org_ids_session,
                hosts_session,
                misc_session,
                config.script_chunk_size,
                logger,
                event_producer,
                notifications_event_producer,
                shutdown_handler.shut_down,
            )
            logger.info(f"Total number of hosts deleted: {num_deleted}")
            return num_deleted

        except InterruptedError:
            logger.info(f"{PROMETHEUS_JOB} was interrupted.")
            return None


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)
    job_type = "Delete duplicate hosts"
    sys.excepthook = partial(excepthook, logger, job_type)

    config, _, event_producer, notifications_event_producer, shutdown_handler, application = job_setup(
        COLLECTED_METRICS, PROMETHEUS_JOB
    )

    SessionMaker = init_db(config)
    org_ids_session = SessionMaker()
    hosts_session = SessionMaker()
    misc_session = SessionMaker()
    register_shutdown(org_ids_session.get_bind().dispose, "Closing database")
    register_shutdown(hosts_session.get_bind().dispose, "Closing database")
    register_shutdown(misc_session.get_bind().dispose, "Closing database")

    with multi_session_guard([org_ids_session, hosts_session, misc_session]):
        run(
            config,
            logger,
            org_ids_session,
            hosts_session,
            misc_session,
            event_producer,
            notifications_event_producer,
            shutdown_handler,
            application,
        )

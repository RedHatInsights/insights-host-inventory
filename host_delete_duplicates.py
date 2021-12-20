import sys
from functools import partial

import flask
from flask_api import status
from prometheus_client import CollectorRegistry
from prometheus_client import push_to_gateway
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import UNKNOWN_REQUEST_ID_VALUE
from app.config import Config
from app.environment import RuntimeEnvironment
from app.logging import configure_logging
from app.logging import get_logger
from app.logging import threadctx
from app.queue.event_producer import EventProducer
from lib.db import multi_session_guard
from lib.handlers import register_shutdown
from lib.handlers import ShutdownHandler
from lib.host_kafka import kafka_available
from lib.host_remove_duplicates import delete_duplicate_hosts
from lib.metrics import delete_duplicate_host_count

__all__ = ("main", "run")

PROMETHEUS_JOB = "duplicate-hosts-remover"
LOGGER_NAME = "duplicate-hosts-remover"
COLLECTED_METRICS = (delete_duplicate_host_count,)
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB


def _init_config():
    config = Config(RUNTIME_ENVIRONMENT)
    config.log_configuration()
    return config


def _init_db(config):
    engine = create_engine(config.db_uri)
    return sessionmaker(bind=engine)


def _prometheus_job(namespace):
    return f"{PROMETHEUS_JOB}-{namespace}" if namespace else PROMETHEUS_JOB


def _excepthook(logger, type, value, traceback):
    logger.exception("Host duplicate remover failed", exc_info=value)


def run(config, logger, accounts_session, hosts_session, misc_session, event_producer, shutdown_handler):
    if kafka_available():
        num_deleted = delete_duplicate_hosts(
            accounts_session,
            hosts_session,
            misc_session,
            config.script_chunk_size,
            logger,
            event_producer,
            shutdown_handler.shut_down,
        )
        logger.info(f"Total number of hosts deleted: {num_deleted}")
        return num_deleted
    else:
        logger.error("Kafka server not available.")
        flask.abort(status.HTTP_503_SERVICE_UNAVAILABLE)


def main(logger):

    config = _init_config()
    registry = CollectorRegistry()

    for metric in COLLECTED_METRICS:
        registry.register(metric)

    job = _prometheus_job(config.kubernetes_namespace)
    prometheus_shutdown = partial(push_to_gateway, config.prometheus_pushgateway, job, registry)
    register_shutdown(prometheus_shutdown, "Pushing metrics")

    Session = _init_db(config)
    accounts_session = Session()
    hosts_session = Session()
    misc_session = Session()
    register_shutdown(accounts_session.get_bind().dispose, "Closing database")
    register_shutdown(hosts_session.get_bind().dispose, "Closing database")
    register_shutdown(misc_session.get_bind().dispose, "Closing database")

    event_producer = EventProducer(config)
    register_shutdown(event_producer.close, "Closing producer")

    shutdown_handler = ShutdownHandler()
    shutdown_handler.register()

    with multi_session_guard([accounts_session, hosts_session, misc_session]):
        run(config, logger, accounts_session, hosts_session, misc_session, event_producer, shutdown_handler)


if __name__ == "__main__":
    configure_logging()

    logger = get_logger(LOGGER_NAME)
    sys.excepthook = partial(_excepthook, logger)

    threadctx.request_id = UNKNOWN_REQUEST_ID_VALUE
    main(logger)

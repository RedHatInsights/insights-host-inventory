import sys
from functools import partial

from prometheus_client import CollectorRegistry
from prometheus_client import push_to_gateway
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import UNKNOWN_REQUEST_ID_VALUE
from app.config import Config
from app.culling import Conditions
from app.environment import RuntimeEnvironment
from app.logging import configure_logging
from app.logging import get_logger
from app.logging import threadctx
from app.models import Host
from app.queue.metrics import event_producer_failure
from app.queue.event_producer import EventProducer
from app.queue.metrics import event_producer_success
from app.queue.metrics import event_serialization_time
from lib.db import session_guard
from lib.handlers import register_shutdown
from lib.handlers import ShutdownHandler
from lib.host_delete import delete_hosts
from lib.host_synchronize import synchronize_hosts
from lib.host_repository import stale_timestamp_filter
from lib.metrics import delete_host_count
from lib.metrics import delete_host_processing_time
from lib.metrics import synchronize_fail_count

import json

__all__ = ("main", "run")

PROMETHEUS_JOB = "inventory-synchronizer"
LOGGER_NAME = "inventory_synchronizer"
COLLECTED_METRICS = (
    delete_host_count,
    delete_host_processing_time,
    synchronize_fail_count,
    event_producer_failure,
    event_producer_success,
    event_serialization_time,
)
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
    logger.exception("Host synchronizer failed", exc_info=value)


# TODO question, do we need a counter
@synchronize_fail_count.count_exceptions()
def run(config, logger, session, event_producer, shutdown_handler):
    conditions = Conditions.from_config(config)
    query_filter = stale_timestamp_filter(*conditions.culled())

    query = session.query(Host)

    update_count = 1
    events = synchronize_hosts(query, event_producer, 1000, shutdown_handler.shut_down)
    for host_id, synchronize in events:
        if synchronize:
            logger.info("Synchronized host: %s", host_id)
            logger.info("Number of hosts synchronized: {}".format(update_count))
            update_count += 1
        else:
            logger.info("Host %s already synchronized. Synchronize event not emitted.", host_id)


def main(logger):

    config = _init_config()

    registry = CollectorRegistry()
    for metric in COLLECTED_METRICS:
        registry.register(metric)

    # TODO enable prometheus by uncommenting the following 3 lines.
    # job = _prometheus_job(config.kubernetes_namespace)
    # prometheus_shutdown = partial(push_to_gateway, config.prometheus_pushgateway, job, registry)
    # register_shutdown(prometheus_shutdown, "Pushing metrics")

    Session = _init_db(config)
    session = Session()
    register_shutdown(session.get_bind().dispose, "Closing database")

    event_producer = EventProducer(config)
    register_shutdown(event_producer.close, "Closing producer")

    shutdown_handler = ShutdownHandler()
    shutdown_handler.register()

    with session_guard(session):
        run(config, logger, session, event_producer, shutdown_handler)

if __name__ == "__main__":
    configure_logging()

    logger = get_logger(LOGGER_NAME)
    sys.excepthook = partial(_excepthook, logger)

    threadctx.request_id = UNKNOWN_REQUEST_ID_VALUE
    main(logger)

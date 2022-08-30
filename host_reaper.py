import sys
from functools import partial

from prometheus_client import CollectorRegistry
from prometheus_client import push_to_gateway
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Config
from app.culling import Conditions
from app.environment import RuntimeEnvironment
from app.instrumentation import log_host_delete_failed
from app.instrumentation import log_host_delete_succeeded
from app.logging import configure_logging
from app.logging import get_logger
from app.logging import threadctx
from app.models import Host
from app.payload_tracker import UNKNOWN_REQUEST_ID_VALUE
from app.queue.event_producer import EventProducer
from app.queue.metrics import event_producer_failure
from app.queue.metrics import event_producer_success
from app.queue.metrics import event_serialization_time
from lib.db import session_guard
from lib.handlers import register_shutdown
from lib.handlers import ShutdownHandler
from lib.host_delete import delete_hosts
from lib.host_repository import exclude_edge_filter
from lib.host_repository import stale_timestamp_filter
from lib.metrics import delete_host_count
from lib.metrics import delete_host_processing_time
from lib.metrics import host_reaper_fail_count

__all__ = ("main", "run")

PROMETHEUS_JOB = "inventory-reaper"
LOGGER_NAME = "host_reaper"
COLLECTED_METRICS = (
    delete_host_count,
    delete_host_processing_time,
    host_reaper_fail_count,
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
    logger.exception("Host reaper failed", exc_info=value)


@host_reaper_fail_count.count_exceptions()
def run(config, logger, session, event_producer, shutdown_handler):
    conditions = Conditions.from_config(config)
    query_filter = exclude_edge_filter(stale_timestamp_filter(*conditions.culled()))
    query = session.query(Host).filter(query_filter)

    events = delete_hosts(query, event_producer, config.host_delete_chunk_size, shutdown_handler.shut_down)
    for host_id, deleted in events:
        if deleted:
            log_host_delete_succeeded(logger, host_id, "REAPER")
        else:
            log_host_delete_failed(logger, host_id, "REAPER")


def main(logger):
    config = _init_config()

    registry = CollectorRegistry()
    for metric in COLLECTED_METRICS:
        registry.register(metric)
    job = _prometheus_job(config.kubernetes_namespace)
    prometheus_shutdown = partial(push_to_gateway, config.prometheus_pushgateway, job, registry)
    register_shutdown(prometheus_shutdown, "Pushing metrics")

    Session = _init_db(config)
    session = Session()
    register_shutdown(session.get_bind().dispose, "Closing database")

    event_producer = EventProducer(config, config.event_topic)
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

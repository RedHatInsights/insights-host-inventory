import sys
from functools import partial

from flask import g
from prometheus_client import CollectorRegistry
from prometheus_client import push_to_gateway
from sqlalchemy import and_
from sqlalchemy import create_engine
from sqlalchemy import or_
from sqlalchemy.orm import sessionmaker

from app import create_app
from app.auth.identity import create_mock_identity_with_org_id
from app.config import Config
from app.config import HOST_TYPES
from app.environment import RuntimeEnvironment
from app.instrumentation import log_host_delete_failed
from app.instrumentation import log_host_delete_succeeded
from app.logging import configure_logging
from app.logging import get_logger
from app.logging import threadctx
from app.models import Host
from app.models import Staleness
from app.queue.event_producer import EventProducer
from app.queue.metrics import event_producer_failure
from app.queue.metrics import event_producer_success
from app.queue.metrics import event_serialization_time
from lib.db import session_guard
from lib.handlers import register_shutdown
from lib.handlers import ShutdownHandler
from lib.host_delete import delete_hosts
from lib.host_repository import find_hosts_by_staleness_reaper
from lib.host_repository import find_hosts_sys_default_staleness
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

app = create_app(RUNTIME_ENVIRONMENT)


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


def filter_culled_hosts_using_custom_staleness(logger, session):
    staleness_objects = session.query(Staleness).all()
    org_ids = []

    with app.app_context():
        query_filters = []
        for staleness_obj in staleness_objects:
            # Validate which host types for a given org_id never get deleted
            logger.debug(f"Looking for hosts from org_id {staleness_obj.org_id} that use custom staleness")
            org_ids.append(staleness_obj.org_id)
            identity = create_mock_identity_with_org_id(staleness_obj.org_id)
            query_filters.append(
                and_(
                    (Host.org_id == staleness_obj.org_id),
                    find_hosts_by_staleness_reaper(["culled"], identity, HOST_TYPES),
                )
            )
            if "acc_st" in g:
                logger.debug("Cleaning account staleness data in g global variable")
                del g.acc_st
        return query_filters, org_ids


def filter_culled_hosts_using_sys_default_staleness(logger, org_ids, query_filters):
    # Use the hosts_ids_list to exclude hosts that were found with custom staleness
    with app.app_context():
        logger.debug("Looking for hosts that use system default staleness")
        query_filters.append(and_(~Host.org_id.in_(org_ids), find_hosts_sys_default_staleness(["culled"], HOST_TYPES)))
        return query_filters


def find_hosts_to_delete(logger, session):
    # Find all host ids that are using custom staleness
    query_filters, org_ids = filter_culled_hosts_using_custom_staleness(logger, session)

    # Find all host ids that are not using custom staleness,
    # excluding the hosts for the org_ids that use custom staleness
    query_filters = filter_culled_hosts_using_sys_default_staleness(logger, org_ids, query_filters)

    return query_filters


@host_reaper_fail_count.count_exceptions()
def run(config, logger, session, event_producer, shutdown_handler):
    filter_hosts_to_delete = find_hosts_to_delete(logger, session)
    query = session.query(Host).filter(or_(False, *filter_hosts_to_delete))

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

    threadctx.request_id = None
    main(logger)

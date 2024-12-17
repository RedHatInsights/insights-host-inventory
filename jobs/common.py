from functools import partial

from prometheus_client import CollectorRegistry
from prometheus_client import push_to_gateway
from sqlalchemy import ColumnElement
from sqlalchemy import and_
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.cache import init_cache
from app import create_app
from app.auth.identity import create_mock_identity_with_org_id
from app.config import Config
from app.environment import RuntimeEnvironment
from app.models import Host
from app.models import Staleness
from app.queue.event_producer import EventProducer
from lib.handlers import ShutdownHandler
from lib.handlers import register_shutdown
from lib.host_repository import find_hosts_by_staleness_job
from lib.host_repository import find_hosts_sys_default_staleness

RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB


def init_config():
    config = Config(RUNTIME_ENVIRONMENT)
    config.log_configuration()
    return config


def init_db(config):
    engine = create_engine(config.db_uri)
    return sessionmaker(bind=engine)


def prometheus_job(namespace, prometheus_job):
    return f"{prometheus_job}-{namespace}" if namespace else prometheus_job


def excepthook(logger, job_type, value, traceback):
    logger.exception("%s failed", job_type, exc_info=value)


def filter_hosts_in_state_using_custom_staleness(logger, session, state: list, config=None):
    staleness_objects = session.query(Staleness).all()
    org_ids = []

    query_filters = []
    for staleness_obj in staleness_objects:
        # Validate which host types for a given org_id never get deleted
        logger.debug(f"Looking for hosts from org_id {staleness_obj.org_id} that use custom staleness")
        org_ids.append(staleness_obj.org_id)
        identity = create_mock_identity_with_org_id(staleness_obj.org_id)
        query_filters.append(
            and_(
                (Host.org_id == staleness_obj.org_id),
                find_hosts_by_staleness_job(state, identity, config),
            )
        )
    return query_filters, org_ids


def filter_hosts_in_state_using_sys_default_staleness(logger, org_ids, state: list, config=None) -> ColumnElement:
    # Use the hosts_ids_list to exclude hosts that were found with custom staleness
    logger.debug("Looking for hosts that use system default staleness")
    return and_(~Host.org_id.in_(org_ids), find_hosts_sys_default_staleness(state, config))


def find_hosts_in_state(logger, session, state: list, config=None):
    # Find all host ids that are using custom staleness
    query_filters, org_ids = filter_hosts_in_state_using_custom_staleness(logger, session, state, config)

    # Find all host ids that are not using custom staleness,
    # excluding the hosts for the org_ids that use custom staleness
    query_filters.append(filter_hosts_in_state_using_sys_default_staleness(logger, org_ids, state, config))

    return query_filters


def main(logger, collected_metrics, prometheus_job_name):
    config = init_config()
    application = create_app(RUNTIME_ENVIRONMENT)
    init_cache(config, application)

    registry = CollectorRegistry()
    for metric in collected_metrics:
        registry.register(metric)
    job = prometheus_job(config.kubernetes_namespace, prometheus_job_name)
    prometheus_shutdown = partial(push_to_gateway, config.prometheus_pushgateway, job, registry)
    register_shutdown(prometheus_shutdown, "Pushing metrics")

    Session = init_db(config)
    session = Session()
    register_shutdown(session.get_bind().dispose, "Closing database")

    event_producer = EventProducer(config, config.event_topic)
    register_shutdown(event_producer.close, "Closing producer")

    notification_event_producer = EventProducer(config, config.notification_topic)
    register_shutdown(notification_event_producer.close, "Closing notification producer")

    shutdown_handler = ShutdownHandler()
    shutdown_handler.register()
    # run(config, logger, session, event_producer, notification_event_producer, shutdown_handler, application)
    return config, logger, session, event_producer, notification_event_producer, shutdown_handler, application

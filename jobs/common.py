from functools import partial

from prometheus_client import CollectorRegistry
from prometheus_client import push_to_gateway
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.cache import init_cache
from app import create_app
from app.config import Config
from app.environment import RuntimeEnvironment
from app.queue.event_producer import EventProducer
from lib.handlers import ShutdownHandler
from lib.handlers import register_shutdown

__all__ = "job_setup"

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


def excepthook(logger, job_type, value, traceback):  # noqa: ARG001, needed by sys.excepthook
    logger.exception("%s failed", job_type, exc_info=value)


def job_setup(collected_metrics: tuple, prometheus_job_name: str):
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
    return config, session, event_producer, notification_event_producer, shutdown_handler, application

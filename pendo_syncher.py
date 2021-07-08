import sys
from functools import partial

from prometheus_client import CollectorRegistry
from prometheus_client import push_to_gateway
from sqlalchemy import create_engine
from sqlalchemy import func
from sqlalchemy.orm import sessionmaker

from app import UNKNOWN_REQUEST_ID_VALUE
from app.config import Config
from app.environment import RuntimeEnvironment
from app.logging import configure_logging
from app.logging import get_logger
from app.logging import threadctx
from app.models import Host
from lib.db import session_guard
from lib.handlers import register_shutdown
from lib.handlers import ShutdownHandler
from lib.metrics import pendo_fetching_failure
from lib.pendo_sync_helpers import pendo_sync


__all__ = ("main", "run")

PROMETHEUS_JOB = "inventory-pendo-syncher"
LOGGER_NAME = "inventory_pendo_syncher"
COLLECTED_METRICS = (pendo_fetching_failure,)
RUNTIME_ENVIRONMENT = RuntimeEnvironment.PENDO_JOB


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
    logger.exception("Pendo Syncher failed", exc_info=value)


@pendo_fetching_failure.count_exceptions()
def run(config, logger, session, shutdown_handler):

    query = session.query(Host.account, func.count(Host.id))

    pendo_sync(query, config.pendo_request_size, config, logger, shutdown_handler.shut_down)
    logger.info("Pendo Syncher Run Complete.")


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

    # event_producer = EventProducer(config)
    # register_shutdown(event_producer.close, "Closing producer")

    shutdown_handler = ShutdownHandler()
    shutdown_handler.register()

    with session_guard(session):
        run(config, logger, session, shutdown_handler)


if __name__ == "__main__":
    configure_logging()

    logger = get_logger(LOGGER_NAME)
    sys.excepthook = partial(_excepthook, logger)

    threadctx.request_id = UNKNOWN_REQUEST_ID_VALUE
    main(logger)

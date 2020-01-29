from os import getenv

from prometheus_client import CollectorRegistry
from prometheus_client import push_to_gateway
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.metrics import delete_host_count
from api.metrics import delete_host_processing_time
from app import UNKNOWN_REQUEST_ID_VALUE
from app.config import Config
from app.config import RuntimeEnvironment
from app.culling import Conditions
from app.logging import configure_logging
from app.logging import get_logger
from app.logging import threadctx
from app.models import Host
from lib.host_delete import delete_hosts
from lib.host_repository import stale_timestamp_filter
from tasks import flush
from tasks import init_tasks


__all__ = ("main",)

PROMETHEUS_JOB = "host_reaper"
COLLECTED_METRICS = (delete_host_count, delete_host_processing_time)


def _init_config(config_name):
    config = Config(RuntimeEnvironment.job)
    config.log_configuration(config_name)
    return config


def _init_db(config):
    engine = create_engine(config.db_uri)
    return sessionmaker(bind=engine)


def _run(config, logger, session):
    conditions = Conditions.from_config(config)
    query_filter = stale_timestamp_filter(*conditions.culled())

    query = session.query(Host).filter(query_filter)

    events = delete_hosts(query)

    if events:
        for deleted_host in events:
            if deleted_host:
                logger.info("Deleted host: %s", deleted_host.id)
            else:
                logger.info("Host already deleted. Delete event not emitted.")
    else:
        logger.info("No hosts deleted.")


def main(config_name):
    config = _init_config(config_name)
    init_tasks(config)

    logger = get_logger("host_reaper")

    registry = CollectorRegistry()
    for metric in COLLECTED_METRICS:
        registry.register(metric)

    Session = _init_db(config)
    session = Session()

    _run(config, logger, session)

    session.commit()
    session.close()

    flush()
    push_to_gateway(config.prometheus_pushgateway, PROMETHEUS_JOB, registry)


if __name__ == "__main__":
    config_name = getenv("APP_SETTINGS", "development")
    configure_logging(config_name)
    threadctx.request_id = UNKNOWN_REQUEST_ID_VALUE
    main(config_name)

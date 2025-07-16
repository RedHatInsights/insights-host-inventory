#!/usr/bin/python
import sys
from functools import partial

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import create_app
from app.config import Config
from app.environment import RuntimeEnvironment
from app.logging import configure_logging
from app.logging import get_logger
from app.logging import threadctx
from app.models import Host
from lib.handlers import ShutdownHandler
from lib.handlers import register_shutdown
from lib.host_synchronize import sync_group_data

__all__ = ("main", "run")

PROMETHEUS_JOB = "inventory-synchronizer"
LOGGER_NAME = "inventory_synchronizer"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB

application = create_app(RUNTIME_ENVIRONMENT)
app = application.app


def _init_config():
    config = Config(RUNTIME_ENVIRONMENT)
    config.log_configuration()
    return config


def _init_db(config):
    engine = create_engine(config.db_uri)
    return sessionmaker(bind=engine)


def _excepthook(logger, type, value, traceback):  # noqa: ARG001, needed by sys.excepthook
    logger.exception("Host synchronizer failed", exc_info=value)


def run(config, logger, session, shutdown_handler):
    query_hosts = session.query(Host).filter(Host.groups == [])
    update_count, failed_count = sync_group_data(query_hosts, config.script_chunk_size, shutdown_handler.shut_down)
    logger.info(f"Total number of host.groups updated: {update_count}")
    logger.info(f"Total number of hosts failed to update: {failed_count}")


def main(logger):
    config = _init_config()

    Session = _init_db(config)
    session = Session()
    register_shutdown(session.get_bind().dispose, "Closing database")

    shutdown_handler = ShutdownHandler()
    shutdown_handler.register()

    with app.app_context():
        run(config, logger, session, shutdown_handler)


if __name__ == "__main__":
    configure_logging()

    logger = get_logger(LOGGER_NAME)
    sys.excepthook = partial(_excepthook, logger)

    threadctx.request_id = None
    main(logger)

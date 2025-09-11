#!/usr/bin/python
import os
import sys
from functools import partial

from sqlalchemy import create_engine
from sqlalchemy import text as sa_text
from sqlalchemy.orm import sessionmaker

from api.cache import init_cache
from app import create_app
from app.config import Config
from app.environment import RuntimeEnvironment
from app.logging import get_logger
from lib.handlers import ShutdownHandler
from lib.handlers import register_shutdown

__all__ = ("main", "run")

LOGGER_NAME = "inventory-migration-runner"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB


def _init_config():
    config = Config(RUNTIME_ENVIRONMENT)
    config.log_configuration()
    return config


def _init_db(config):
    engine = create_engine(config.db_uri)
    return sessionmaker(bind=engine)


def _excepthook(logger, type, value, traceback):  # noqa: ARG001, needed by sys.excepthook
    logger.exception("Inventory migration failed", exc_info=value)


def run(logger, session, application):
    with application.app.app_context():
        basedir = os.path.abspath(os.path.dirname(__file__))
        dry_run = os.environ.get("INVENTORY_MIGRATION_DRYRUN", "false")
        migration_file = os.environ.get("INVENTORY_MIGRATION_FILE")
        file_path = os.path.join(basedir, "app_migrations", migration_file)
        if not os.path.isfile(file_path):
            logger.warning(f"No migration file found for given {file_path}.")
            return
        with open(file_path) as file:
            sql_statements = file.read()
            logger.info(f"Executing the following SQL statements:\n{sql_statements}")
            if dry_run.lower() != "true":
                results = session.execute(sa_text(sql_statements))
                try:
                    for row in results:
                        logger.info(f"{row._asdict()}")
                except Exception:
                    pass


def main(logger):
    config = _init_config()
    application = create_app(RUNTIME_ENVIRONMENT)
    init_cache(config, application)

    Session = _init_db(config)
    session = Session()
    register_shutdown(session.get_bind().dispose, "Closing database")

    shutdown_handler = ShutdownHandler()
    shutdown_handler.register()
    run(logger, session, application)


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)
    sys.excepthook = partial(_excepthook, logger)

    main(logger)

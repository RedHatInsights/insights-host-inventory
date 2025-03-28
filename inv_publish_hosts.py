#!/usr/bin/python
import sys
from functools import partial

from prometheus_client import CollectorRegistry
from prometheus_client import push_to_gateway
from sqlalchemy import create_engine
from sqlalchemy import text as sa_text
from sqlalchemy.orm import sessionmaker

from app import create_app
from app.config import Config
from app.environment import RuntimeEnvironment
from app.logging import get_logger
from lib.handlers import ShutdownHandler
from lib.handlers import register_shutdown
from lib.metrics import hosts_syndication_fail_count
from lib.metrics import hosts_syndication_success_count
from lib.metrics import hosts_syndication_time

__all__ = ("main", "run")

LOGGER_NAME = "hosts-syndicator"
PROMETHEUS_JOB = "hosts-syndicator"
COLLECTED_METRICS = (
    hosts_syndication_fail_count,
    hosts_syndication_success_count,
    hosts_syndication_time,
)

RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB

PUBLICATION_NAME = "hbi_hosts_pub_v1"
PUBLICATION_COLUMNS = "id,account,display_name,created_on,modified_on,facts,canonical_facts, \
system_profile_facts,ansible_host,stale_timestamp,reporter,per_reporter_staleness,org_id,groups,tags_alt,last_check_in"
CHECK_PUBLICATION = f"SELECT EXISTS(SELECT * FROM pg_catalog.pg_publication WHERE pubname = '{PUBLICATION_NAME}')"
CREATE_PUBLICATION = f"CREATE PUBLICATION {PUBLICATION_NAME} FOR TABLE hbi.hosts ({PUBLICATION_COLUMNS}) \
WHERE (hbi.hosts.canonical_facts->'insights_id' IS NOT NULL)"
CHECK_REPLICATION_SLOTS = "SELECT slot_name, active FROM pg_replication_slots"


def _init_config():
    config = Config(RUNTIME_ENVIRONMENT)
    config.log_configuration()
    return config


def _init_db(config):
    engine = create_engine(config.db_uri)
    return sessionmaker(bind=engine)


def _prometheus_job(namespace):
    return f"{PROMETHEUS_JOB}-{namespace}" if namespace else PROMETHEUS_JOB


def _excepthook(logger, type, value, traceback):  # noqa: ARG001, needed by sys.excepthook
    logger.exception("Inventory migration failed", exc_info=value)


def run(logger, session, application):
    with application.app.app_context():
        logger.info(f"Checking for publication using the following SQL statement:\n\t{CHECK_PUBLICATION}")
        result = session.execute(sa_text(CHECK_PUBLICATION))
        found = result.cursor.fetchone()[0]
        if found:
            logger.info(f'Publication "{PUBLICATION_NAME}" found!')
        else:
            logger.info(f'Creating publication "{PUBLICATION_NAME}" using \n\t{CREATE_PUBLICATION}')
            try:
                session.execute(sa_text(CREATE_PUBLICATION))

                # check for inactive replication_slots
                replication_slots = session.execute(sa_text(CHECK_REPLICATION_SLOTS)).all()
                inactive = 0
                for slot in replication_slots:
                    slot_name, active = slot
                    if not active:
                        inactive += 1
                        logger.error(f"Replication slot named {slot_name} is not active")
                    if inactive > 0:
                        exit(1)
            except Exception as e:
                session.rollback()
                logger.error(f'Error encountered when creating the publication "{PUBLICATION_NAME}" \n\t{e}')
                hosts_syndication_fail_count.inc()
                raise e
            else:
                session.commit()
                logger.info(f'Publication "{PUBLICATION_NAME}" created!!!')

        hosts_syndication_success_count.inc()


def main(logger):
    config = _init_config()
    application = create_app(RUNTIME_ENVIRONMENT)

    registry = CollectorRegistry()
    for metric in COLLECTED_METRICS:
        registry.register(metric)
    job = _prometheus_job(config.kubernetes_namespace)
    prometheus_shutdown = partial(push_to_gateway, config.prometheus_pushgateway, job, registry)
    register_shutdown(prometheus_shutdown, "Pushing metrics")

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

#!/usr/bin/python
import sys
from functools import partial

from prometheus_client import CollectorRegistry
from prometheus_client import push_to_gateway
from sqlalchemy import create_engine
from sqlalchemy import text
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
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB

# Publications and columns
PUBLICATION_NAME = "hbi_hosts_pub_v1_0_2"
HOSTS_PUBLICATION_COLUMNS = (
    "org_id,id,account,display_name,created_on,modified_on,facts,"
    "ansible_host,insights_id,subscription_manager_id,satellite_id,fqdn,"
    "bios_uuid,ip_addresses,mac_addresses,provider_id,provider_type,"
    "stale_timestamp,reporter,per_reporter_staleness,groups,tags_alt,"
    "last_check_in,stale_warning_timestamp,deletion_timestamp"
)
SP_DYNAMIC_PUBLICATION_COLUMNS = "org_id,host_id,installed_packages,installed_products,workloads"
SP_STATIC_PUBLICATION_COLUMNS = (
    "org_id,host_id,arch,bootc_status,dnf_modules,host_type,image_builder,"
    "operating_system,owner_id,releasever,rhc_client_id,rhsm,satellite_managed,"
    "system_update_method,yum_repos"
)

# Publications to drop
DROP_PUBLICATIONS = [
    "hbi_hosts_pub",
    "hbi_hosts_pub_v1_0_0",
    "hbi_hosts_pub_v1_0_1",
]

# Replication slots to drop
DROP_REPLICATION_SLOTS = ["roadmap_hosts_sub"]

CHECK_PUBLICATION_SQL = text("""
    SELECT EXISTS(
        SELECT 1 FROM pg_catalog.pg_publication WHERE pubname = :pubname
    )
""")
CHECK_REPLICATION_SLOTS_SQL = text("SELECT slot_name, active FROM pg_replication_slots")

CREATE_PUBLICATION_SQL = text(f"""
    CREATE PUBLICATION {PUBLICATION_NAME}
    FOR TABLE
      hbi.hosts ({HOSTS_PUBLICATION_COLUMNS}),
      hbi.system_profiles_dynamic ({SP_DYNAMIC_PUBLICATION_COLUMNS}),
      hbi.system_profiles_static ({SP_STATIC_PUBLICATION_COLUMNS})
    WHERE (insights_id != '00000000-0000-0000-0000-000000000000')
    WITH (publish_via_partition_root = true);
""")

DROP_PUBLICATION_SQL = "DROP PUBLICATION IF EXISTS "

DROP_REPLICATION_SLOTS_SQL = text("SELECT pg_drop_replication_slot(:slot_name)")

COLLECTED_METRICS = (
    hosts_syndication_fail_count,
    hosts_syndication_success_count,
    hosts_syndication_time,
)


def _init_config():
    config = Config(RUNTIME_ENVIRONMENT)
    config.log_configuration()
    return config


def _init_db(config):
    engine = create_engine(config.db_uri)
    return sessionmaker(bind=engine)


def _prometheus_job(namespace):
    return f"{PROMETHEUS_JOB}-{namespace}" if namespace else PROMETHEUS_JOB


def _excepthook(logger, exc_type, value, traceback):  # noqa
    logger.exception("Inventory migration failed", exc_info=value)


def drop_old_publications(session, logger):
    for pub in DROP_PUBLICATIONS:
        logger.info(f"Dropping publication: {pub}")
        session.execute(text(DROP_PUBLICATION_SQL + pub))


def publication_exists(session, logger):
    found = session.execute(CHECK_PUBLICATION_SQL, {"pubname": PUBLICATION_NAME}).scalar()
    if found:
        logger.info(f'Publication "{PUBLICATION_NAME}" found!')
    return found


def create_publication(session, logger):
    logger.info(f'Creating publication "{PUBLICATION_NAME}".')
    session.execute(CREATE_PUBLICATION_SQL)
    logger.info(f'Publication "{PUBLICATION_NAME}" created!')


def check_and_drop_inactive_slots(session, logger):
    slots = session.execute(CHECK_REPLICATION_SLOTS_SQL).all()
    inactive_slots = [slot_name for slot_name, active in slots if not active]

    for slot_name in inactive_slots:
        if slot_name in DROP_REPLICATION_SLOTS:
            logger.info(f"Dropping inactive replication slot: {slot_name}")
            session.execute(DROP_REPLICATION_SLOTS_SQL, {"slot_name": slot_name})
        else:
            raise Exception(f"Replication slot '{slot_name}' is inactive. Aborting.")


def run(logger, session, application):
    with application.app.app_context():
        try:
            drop_old_publications(session, logger)
            if not publication_exists(session, logger):
                create_publication(session, logger)
                check_and_drop_inactive_slots(session, logger)
        except Exception as e:
            session.rollback()
            hosts_syndication_fail_count.inc()
            logger.error(f"Error during publication setup: {e}")
            raise
        else:
            session.commit()
            hosts_syndication_success_count.inc()
            logger.info("Publication setup completed successfully.")


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

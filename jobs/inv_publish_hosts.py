#!/usr/bin/python3
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
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB

# Publications and columns
PUBLICATION_NAME = "hbi_hosts_pub_v1_0_2"
HOSTS_PUBLICATION_COLUMNS = [
    "org_id",
    "id",
    "account",
    "display_name",
    "ansible_host",
    "created_on",
    "modified_on",
    "facts",
    "tags_alt",
    "groups",
    "last_check_in",
    "stale_timestamp",
    "deletion_timestamp",
    "stale_warning_timestamp",
    "reporter",
    "per_reporter_staleness",
    "insights_id",
    "subscription_manager_id",
    "satellite_id",
    "fqdn",
    "bios_uuid",
    "ip_addresses",
    "mac_addresses",
    "provider_id",
    "provider_type",
]
SP_DYNAMIC_PUBLICATION_COLUMNS = [
    "org_id",
    "host_id",
    "insights_id",
    "installed_packages",
    "installed_products",
    "workloads",
]
SP_STATIC_PUBLICATION_COLUMNS = (
    "org_id",
    "host_id",
    "insights_id",
    "arch",
    "bootc_status",
    "dnf_modules",
    "host_type",
    "image_builder",
    "operating_system",
    "owner_id",
    "releasever",
    "rhc_client_id",
    "rhsm",
    "satellite_managed",
    "system_update_method",
    "yum_repos",
)

# Publications to drop
DROP_PUBLICATIONS = [
    "hbi_hosts_pub",
    "hbi_hosts_pub_v1_0_0",
    "hbi_hosts_pub_v1_0_1",
]

# Replication slots to drop
DROP_REPLICATION_SLOTS = ["roadmap_hosts_sub"]

CHECK_PUBLICATION_SQL = sa_text("""
    SELECT EXISTS(
        SELECT 1 FROM pg_catalog.pg_publication WHERE pubname = :pubname
    )
""")
CHECK_REPLICATION_SLOTS_SQL = sa_text("SELECT slot_name, active FROM pg_replication_slots")

CREATE_PUBLICATION_SQL = sa_text(f"""
    CREATE PUBLICATION {PUBLICATION_NAME}
    FOR TABLE
      hbi.hosts ({",".join(HOSTS_PUBLICATION_COLUMNS)})
        WHERE (insights_id != '00000000-0000-0000-0000-000000000000'),
      hbi.system_profiles_dynamic ({",".join(SP_DYNAMIC_PUBLICATION_COLUMNS)})
        WHERE (insights_id != '00000000-0000-0000-0000-000000000000'),
      hbi.system_profiles_static ({",".join(SP_STATIC_PUBLICATION_COLUMNS)})
        WHERE (insights_id != '00000000-0000-0000-0000-000000000000')
    WITH (publish_via_partition_root = true);
""")

DROP_PUBLICATION_SQL = "DROP PUBLICATION IF EXISTS "

DROP_REPLICATION_SLOTS_SQL = sa_text("SELECT pg_drop_replication_slot(:slot_name)")

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


def _excepthook(logger, exc_type, value, traceback):
    logger.exception("Inventory migration failed", exc_info=(exc_type, value, traceback))


def setup_publication(session, logger):
    # 1) drop any legacy publications
    for pub in DROP_PUBLICATIONS:
        logger.info(f"Dropping publication: {pub}")
        session.execute(sa_text(DROP_PUBLICATION_SQL + pub))

    # 2) check if the publication already exists
    exists = session.execute(CHECK_PUBLICATION_SQL, {"pubname": PUBLICATION_NAME}).scalar()
    if exists:
        logger.info(f'Publication "{PUBLICATION_NAME}" already exists.')
        return

    # 3) create the publication
    logger.info(f'Creating publication "{PUBLICATION_NAME}".')
    session.execute(CREATE_PUBLICATION_SQL)

    # 4) sanity-check replication slots
    bad = []
    for slot_name, active in session.execute(CHECK_REPLICATION_SLOTS_SQL):
        if not active:
            if slot_name in DROP_REPLICATION_SLOTS:
                logger.info(f"Dropping inactive slot: {slot_name}")
                session.execute(DROP_REPLICATION_SLOTS_SQL, {"slot_name": slot_name})
            else:
                bad.append(slot_name)
    if bad:
        raise RuntimeError(f"Inactive slots left open: {bad}")

    logger.info(f'Publication "{PUBLICATION_NAME}" created!')


def run(logger, session, application):
    with application.app.app_context():
        try:
            setup_publication(session, logger)
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

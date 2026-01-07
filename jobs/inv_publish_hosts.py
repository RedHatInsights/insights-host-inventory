#!/usr/bin/python3
import os
import sys
from functools import partial

from prometheus_client import CollectorRegistry
from prometheus_client import push_to_gateway
from sqlalchemy import create_engine
from sqlalchemy import text as sa_text
from sqlalchemy.orm import sessionmaker

from app import create_app
from app.config import DEFAULT_INSIGHTS_ID
from app.config import Config
from app.environment import RuntimeEnvironment
from app.logging import get_logger
from app.models.constants import INVENTORY_SCHEMA
from lib.handlers import ShutdownHandler
from lib.handlers import register_shutdown
from lib.metrics import hosts_syndication_fail_count
from lib.metrics import hosts_syndication_success_count
from lib.metrics import hosts_syndication_time

__all__ = ("main", "run")

LOGGER_NAME = "hosts-syndicator"
PROMETHEUS_JOB = "hosts-syndicator"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB

# Configuration from environment variables
CREATE_PUBLICATIONS = [pub.strip() for pub in os.getenv("CREATE_PUBLICATIONS", "").split(",") if pub.strip()]
DROP_PUBLICATIONS = [pub.strip() for pub in os.getenv("DROP_PUBLICATIONS", "").split(",") if pub.strip()]
DROP_REPLICATION_SLOTS = [slot.strip() for slot in os.getenv("DROP_REPLICATION_SLOTS", "").split(",") if slot.strip()]
REPLICA_IDENTITY_MODE = os.getenv("REPLICA_IDENTITY_MODE", "").lower()


# Publication configurations for replica identity management and publication setup
PUBLICATION_CONFIG = {
    "hbi_hosts_pub_v1_0_2": {
        "tables": [
            {
                "name": "hosts",
                "schema": INVENTORY_SCHEMA,
                "has_partitions": True,
                "publication_columns": [
                    "org_id",
                    "id",
                    "account",
                    "display_name",
                    "created_on",
                    "modified_on",
                    "tags_alt",
                    "groups",
                    "last_check_in",
                    "stale_timestamp",
                    "deletion_timestamp",
                    "stale_warning_timestamp",
                    "reporter",
                    "per_reporter_staleness",
                    "insights_id",
                ],
                "publication_filter": f"insights_id != '{DEFAULT_INSIGHTS_ID}'",
            },
            {
                "name": "system_profiles_dynamic",
                "schema": INVENTORY_SCHEMA,
                "has_partitions": True,
                "publication_columns": [
                    "org_id",
                    "host_id",
                    "insights_id",
                    "installed_packages",
                    "installed_products",
                    "workloads",
                ],
                "publication_filter": f"insights_id != '{DEFAULT_INSIGHTS_ID}'",
            },
            {
                "name": "system_profiles_static",
                "schema": INVENTORY_SCHEMA,
                "has_partitions": True,
                "publication_columns": [
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
                ],
                "publication_filter": f"insights_id != '{DEFAULT_INSIGHTS_ID}'",
            },
        ]
    }
}

CHECK_PUBLICATION_SQL = sa_text("""
    SELECT EXISTS(
        SELECT 1 FROM pg_catalog.pg_publication WHERE pubname = :pubname
    )
""")
CHECK_REPLICATION_SLOTS_SQL = sa_text("SELECT slot_name, active FROM pg_replication_slots")

DROP_PUBLICATION_SQL = "DROP PUBLICATION IF EXISTS "

DROP_REPLICATION_SLOTS_SQL = sa_text("SELECT pg_drop_replication_slot(:slot_name)")

REPLICA_IDENTITY_DEFAULT_SQL = sa_text("ALTER TABLE {schema}.{table_name} REPLICA IDENTITY DEFAULT")
REPLICA_IDENTITY_INDEX_SQL = sa_text("ALTER TABLE {schema}.{table_name} REPLICA IDENTITY USING INDEX {index_name}")

GET_PARTITIONS_SQL = sa_text("""
    SELECT schemaname, tablename
    FROM pg_tables
    WHERE schemaname = :schema
    AND tablename ~ :table_pattern
    AND tablename != :table_name
    ORDER BY tablename
""")

GET_CURRENT_REPLICA_IDENTITY_SQL = sa_text("""
    SELECT relreplident
    FROM pg_class
    WHERE oid = (:qualified_table_name)::regclass
""")

# Get the unique index for replica identity
GET_UNIQUE_INDEXES_SQL = sa_text("""
    SELECT indexname
    FROM pg_indexes
    WHERE schemaname = :schema
    AND tablename = :table_name
    AND indexdef LIKE '%UNIQUE%'
    AND (indexname LIKE '%replica_identity%'
         OR indexname LIKE '%org_id_id_insights_id_idx%'
         OR indexname LIKE '%org_id_host_id_insights_id_idx%')
    ORDER BY indexname
    LIMIT 1
""")

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


def _build_create_publication_sql(publication_name):
    """Build CREATE PUBLICATION SQL dynamically from PUBLICATION_CONFIG."""
    if publication_name not in PUBLICATION_CONFIG:
        raise ValueError(f"Publication '{publication_name}' not found in PUBLICATION_CONFIG")

    publication_config = PUBLICATION_CONFIG[publication_name]
    table_specs = []

    for table_config in publication_config["tables"]:
        table_name = table_config["name"]
        schema = table_config["schema"]
        columns = ",".join(table_config["publication_columns"])
        publication_filter = table_config.get("publication_filter", "")

        if publication_filter:
            table_spec = f"""{schema}.{table_name} ({columns}) WHERE ({publication_filter})"""
        else:
            table_spec = f"""{schema}.{table_name} ({columns})"""

        table_specs.append(table_spec)

    return sa_text(f"""
        CREATE PUBLICATION {publication_name}
        FOR TABLE
        {",\n".join(table_specs)}
        WITH (publish_via_partition_root = true);
    """)


def set_replica_identity_for_table(session, logger, table_config, mode="index"):
    """Set replica identity for a table and its partitions."""
    table_name = table_config["name"]
    schema = table_config["schema"]
    has_partitions = table_config["has_partitions"]

    logger.info(f"Setting replica identity to '{mode}' for table {schema}.{table_name}")

    # Set replica identity for the main table
    _set_replica_identity_single_table(session, logger, schema, table_name, mode)

    # Set replica identity for partitions if they exist
    if has_partitions:
        partitions = session.execute(
            GET_PARTITIONS_SQL,
            {"schema": schema, "table_name": table_name, "table_pattern": f"^{table_name}_p[0-9]+$"},
        ).fetchall()

        for partition_schema, partition_name in partitions:
            _set_replica_identity_single_table(session, logger, partition_schema, partition_name, mode)


def _get_current_replica_identity_mode(session, schema, table_name):
    """
    Get the current replica identity mode for a table.
    Returns: 'default', 'index', or 'unknown'
    """
    qualified_table_name = f"{schema}.{table_name}"

    try:
        replica_identity_result = session.execute(
            GET_CURRENT_REPLICA_IDENTITY_SQL, {"qualified_table_name": qualified_table_name}
        ).fetchone()

        if not replica_identity_result:
            return "unknown"

        relreplident = replica_identity_result[0]

        # Map PostgreSQL replica identity codes to our modes
        # 'd' = default, 'i' = index, 'f' = full, 'n' = nothing
        if relreplident == "d":
            return "default"
        elif relreplident == "i":
            return "index"
        return "unknown"
    except Exception:
        # If table doesn't exist or any other error, return unknown
        return "unknown"


def _set_replica_identity_single_table(session, logger, schema, table_name, mode):
    """Set replica identity for a single table."""
    sql = None
    sql_params = None
    try:
        current_mode = _get_current_replica_identity_mode(session, schema, table_name)

        if current_mode == mode:
            logger.info(f"Table {schema}.{table_name} already has replica identity {mode.upper()} - skipping")
            return

        logger.info(
            f"Changing replica identity for {schema}.{table_name} from {current_mode.upper()} to {mode.upper()}"
        )

        if mode == "default":
            sql = REPLICA_IDENTITY_DEFAULT_SQL.text.format(schema=schema, table_name=table_name)
            sql_params = None
            session.execute(sa_text(sql))
            logger.info(f"Set replica identity DEFAULT for {schema}.{table_name}")

        elif mode == "index":
            sql_params = {"schema": schema, "table_name": table_name}
            index_result = session.execute(GET_UNIQUE_INDEXES_SQL, sql_params).fetchone()

            if index_result:
                index_name = index_result[0]
                sql = REPLICA_IDENTITY_INDEX_SQL.text.format(
                    schema=schema, table_name=table_name, index_name=index_name
                )
                session.execute(sa_text(sql))
                logger.info(f"Set replica identity USING INDEX {index_name} for {schema}.{table_name}")
            else:
                # Fallback to default if no suitable index found
                logger.warning(f"No suitable unique index found for {schema}.{table_name}, using DEFAULT")
                sql = REPLICA_IDENTITY_DEFAULT_SQL.text.format(schema=schema, table_name=table_name)
                session.execute(sa_text(sql))

        else:
            raise ValueError(f"Invalid replica identity mode: {mode}. Use 'default' or 'index'")
    except Exception as exc:
        logger.error(
            f"Error setting replica identity for {schema}.{table_name} with mode '{mode}'. "
            f"SQL: {sql!r}, Params: {sql_params!r}, Exception: {exc}",
            exc_info=True,
        )
        raise


def configure_replica_identities(session, logger):
    """Configure replica identities for all tables across all publications in PUBLICATION_CONFIG."""
    if REPLICA_IDENTITY_MODE == "":
        logger.info("Replica identity configuration skipped (REPLICA_IDENTITY_MODE is empty)")
        return

    if REPLICA_IDENTITY_MODE not in ["default", "index"]:
        logger.error(
            f"Invalid REPLICA_IDENTITY_MODE: {REPLICA_IDENTITY_MODE}. Must be 'default', 'index', or empty string"
        )
        return

    logger.info(f"Configuring replica identities with mode: {REPLICA_IDENTITY_MODE}")

    # Collect all unique tables across all publication configurations
    unique_tables = {}
    for publication_config in PUBLICATION_CONFIG.values():
        for table_config in publication_config["tables"]:
            table_key = f"{table_config['schema']}.{table_config['name']}"
            if table_key not in unique_tables:
                unique_tables[table_key] = table_config

    # Configure replica identity for each unique table
    for table_config in unique_tables.values():
        set_replica_identity_for_table(session, logger, table_config, REPLICA_IDENTITY_MODE)


def setup_publication(session, logger):
    """Setup publications and manage replication slots based on configuration."""

    if DROP_PUBLICATIONS:
        logger.info(f"Dropping publications: {DROP_PUBLICATIONS}")
        for pub in DROP_PUBLICATIONS:
            logger.info(f"Dropping publication: {pub}")
            session.execute(sa_text(DROP_PUBLICATION_SQL + pub))
    else:
        logger.info("No publications configured for dropping")

    if CREATE_PUBLICATIONS:
        logger.info(f"Creating publications: {CREATE_PUBLICATIONS}")
        for publication_name in CREATE_PUBLICATIONS:
            exists = session.execute(CHECK_PUBLICATION_SQL, {"pubname": publication_name}).scalar()
            if exists:
                logger.info(f'Publication "{publication_name}" already exists.')
            else:
                logger.info(f'Creating publication "{publication_name}".')
                create_sql = _build_create_publication_sql(publication_name)
                session.execute(create_sql)
                logger.info(f'Publication "{publication_name}" created!')
    else:
        logger.info("No publications configured for creation")

    # sanity-check replication slots
    if DROP_REPLICATION_SLOTS:
        logger.info(f"Checking replication slots to drop: {DROP_REPLICATION_SLOTS}")
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
    else:
        logger.info("No replication slots configured for cleanup")


def run(logger, session, application):
    with application.app.app_context():
        try:
            logger.info("Configuring replica identities...")
            configure_replica_identities(session, logger)

            logger.info("Setting up publications...")
            setup_publication(session, logger)
        except Exception as e:
            session.rollback()
            hosts_syndication_fail_count.inc()
            logger.error(f"Error during setup: {e}")
            raise
        else:
            session.commit()
            hosts_syndication_success_count.inc()
            logger.info("Setup completed successfully.")


def main(logger):
    logger.info("Starting hosts syndicator with configuration:")
    logger.info(f"  CREATE_PUBLICATIONS: {CREATE_PUBLICATIONS}")
    logger.info(f"  DROP_PUBLICATIONS: {DROP_PUBLICATIONS}")
    logger.info(f"  DROP_REPLICATION_SLOTS: {DROP_REPLICATION_SLOTS}")
    logger.info(f"  REPLICA_IDENTITY_MODE: {REPLICA_IDENTITY_MODE}")

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

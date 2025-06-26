#!/usr/bin/python
# ruff: noqa: E501
import os
import sys
from functools import partial
from logging import Logger

from connexion import FlaskApp
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.environment import RuntimeEnvironment
from app.logging import get_logger
from jobs.common import excepthook
from jobs.common import job_setup
from lib.db import session_guard

PROMETHEUS_JOB = "hosts-table-partitioning"
LOGGER_NAME = "hosts_table_partitioning"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB

INVENTORY_SCHEMA = "hbi"
NUM_PARTITIONS = int(os.getenv("HOSTS_TABLE_NUM_PARTITIONS", 32))

"""
This job creates a new table called hosts_new and partitions it by org_id.
It also creates a trigger to migrate data from the hosts table to the hosts_new table.

This is intended to be run only once and only on the stage and production databases.
"""


def validate_inputs():
    """Validate input parameters"""
    if not 1 <= NUM_PARTITIONS <= 32:
        raise ValueError(f"Invalid number of partitions: {NUM_PARTITIONS}. Must be between 1 and 32.")


def execute_sql(session: Session, sql_template: str, operation_name: str = ""):
    """Execute SQL with proper error handling and logging."""
    try:
        session.execute(text(sql_template))
    except Exception as e:
        raise RuntimeError(f"Failed to execute {operation_name}: {str(e)}") from e


def create_hosts_new_table(session: Session, logger: Logger):
    """Create the partitioned hosts_new table."""
    logger.info("Creating hosts_new table structure")

    create_table_sql = f"""
        CREATE TABLE {INVENTORY_SCHEMA}.hosts_new (
            org_id varchar(36) NOT NULL,
            id uuid NOT NULL,
            account varchar(10) NULL,
            display_name varchar(200) NULL,
            ansible_host varchar(255) NULL,
            created_on timestamptz NULL,
            modified_on timestamptz NULL,
            facts jsonb NULL,
            tags jsonb NULL,
            tags_alt jsonb NULL,
            system_profile_facts jsonb NULL,
            "groups" jsonb NULL,
            last_check_in timestamptz NULL,
            stale_timestamp timestamptz NULL,
            deletion_timestamp timestamptz NULL,
            stale_warning_timestamp timestamptz NULL,
            reporter varchar(255) NULL,
            per_reporter_staleness jsonb NULL,
            canonical_facts jsonb NOT NULL,
            canonical_facts_version int4 NULL,
            is_virtual bool NULL,
            insights_id varchar(36) NULL,
            subscription_manager_id varchar(36) NULL,
            satellite_id varchar(255) NULL,
            fqdn varchar(255) NULL,
            bios_uuid varchar(36) NULL,
            ip_addresses jsonb NULL,
            mac_addresses jsonb NULL,
            provider_id varchar(500) NULL,
            provider_type varchar(50) NULL,
            CONSTRAINT hosts_new_pkey PRIMARY KEY (org_id, id)
        )
        PARTITION BY HASH (org_id);
    """

    execute_sql(session, create_table_sql, operation_name="table creation")
    logger.info("Successfully created hosts_new table structure")


def create_partitions(session: Session, logger: Logger):
    logger.info(f"Creating {NUM_PARTITIONS} partitions")

    for i in range(NUM_PARTITIONS):
        partition_name = f"hosts_p{i}"

        partition_sql = f"""
            CREATE TABLE {INVENTORY_SCHEMA}.{partition_name}
            PARTITION OF {INVENTORY_SCHEMA}.hosts_new
            FOR VALUES WITH (MODULUS {NUM_PARTITIONS}, REMAINDER {i});
        """

        execute_sql(session, partition_sql, operation_name=f"partition {partition_name} creation")

    logger.info(f"Successfully created all {NUM_PARTITIONS} partitions")


def create_essential_indexes(session: Session, logger: Logger):
    """Create essential indexes."""
    logger.info("Creating essential indexes")

    essential_indexes = [
        (
            f"CREATE INDEX idx_hosts_modified_on_id ON {INVENTORY_SCHEMA}.hosts_new USING btree (modified_on DESC, id DESC);",
            "modified_on pagination index",
        ),
        # Canonical facts column indexes (essential for deduplication)
        (
            f"CREATE INDEX idx_hosts_insights_id ON {INVENTORY_SCHEMA}.hosts_new USING btree (insights_id);",
            "insights_id index",
        ),
        (
            f"CREATE INDEX idx_hosts_subscription_manager_id ON {INVENTORY_SCHEMA}.hosts_new USING btree (subscription_manager_id);",
            "subscription_manager_id index",
        ),
    ]

    for sql, description in essential_indexes:
        execute_sql(session, sql, operation_name=description)

    logger.info("Successfully created essential indexes")


def create_jsonb_indexes(session: Session, logger: Logger):
    """Create GIN indexes for JSONB columns."""
    logger.info("Creating JSONB indexes")

    jsonb_indexes = [
        (
            f"CREATE INDEX idx_hosts_canonical_facts_gin ON {INVENTORY_SCHEMA}.hosts_new USING gin (canonical_facts);",
            "canonical_facts GIN index",
        ),
        (f"CREATE INDEX idx_hosts_groups_gin ON {INVENTORY_SCHEMA}.hosts_new USING gin (groups);", "groups GIN index"),
    ]

    for sql, description in jsonb_indexes:
        execute_sql(session, sql, operation_name=description)

    logger.info("Successfully created JSONB indexes")


def create_functional_indexes(session: Session, logger: Logger):
    """Create functional indexes for JSONB field extraction."""
    logger.info("Creating functional indexes")

    functional_indexes = [
        # Host type index (frequently used for filtering)
        (
            f"""CREATE INDEX idx_hosts_host_type
             ON {INVENTORY_SCHEMA}.hosts_new USING btree ((system_profile_facts ->> 'host_type'::text));""",
            "host_type functional index",
        ),
        # Canonical facts extraction indexes (for backward compatibility)
        (
            f"""CREATE INDEX idx_hosts_cf_insights_id
             ON {INVENTORY_SCHEMA}.hosts_new USING btree ((canonical_facts ->> 'insights_id'::text));""",
            "canonical_facts insights_id index",
        ),
        (
            f"""CREATE INDEX idx_hosts_cf_subscription_manager_id
             ON {INVENTORY_SCHEMA}.hosts_new USING btree (((canonical_facts ->> 'subscription_manager_id'::text)));""",
            "canonical_facts subscription_manager_id index",
        ),
        # System profile facts extraction indexes
        (
            f"""CREATE INDEX idx_hosts_mssql
             ON {INVENTORY_SCHEMA}.hosts_new USING btree (((system_profile_facts ->> 'mssql'::text)));""",
            "mssql functional index",
        ),
        (
            f"""CREATE INDEX idx_hosts_ansible
             ON {INVENTORY_SCHEMA}.hosts_new USING btree (((system_profile_facts ->> 'ansible'::text)));""",
            "ansible functional index",
        ),
        (
            f"""CREATE INDEX idx_hosts_sap_system
             ON {INVENTORY_SCHEMA}.hosts_new USING btree ((((system_profile_facts ->> 'sap_system'::text))::boolean));""",
            "sap_system functional index",
        ),
    ]

    for sql, description in functional_indexes:
        execute_sql(session, sql, operation_name=description)

    logger.info("Successfully created functional indexes")


def create_composite_indexes(session: Session, logger: Logger):
    """Create composite indexes for common query patterns."""
    logger.info("Creating composite indexes")

    composite_indexes = [
        # Common query pattern: org_id + host_type + modified_on
        (
            f"""CREATE INDEX idx_hosts_host_type_modified_on_org_id
             ON {INVENTORY_SCHEMA}.hosts_new USING btree (org_id, modified_on, ((system_profile_facts ->> 'host_type'::text)));""",
            "composite host_type query index",
        ),
        # Bootc status composite index
        (
            f"""CREATE INDEX idx_hosts_bootc_status
             ON {INVENTORY_SCHEMA}.hosts_new USING btree (org_id) WHERE ((((system_profile_facts -> 'bootc_status'::text) -> 'booted'::text) ->> 'image_digest'::text) IS NOT NULL);
            """,
            "bootc_status composite index",
        ),
        # Operating system multi-column index with WHERE clause
        (
            f"""CREATE INDEX idx_hosts_operating_system_multi
             ON {INVENTORY_SCHEMA}.hosts_new USING btree ((((system_profile_facts -> 'operating_system'::text) ->> 'name'::text)), ((((system_profile_facts -> 'operating_system'::text) ->> 'major'::text))::integer), ((((system_profile_facts -> 'operating_system'::text) ->> 'minor'::text))::integer), ((system_profile_facts ->> 'host_type'::text)), modified_on, org_id) WHERE ((system_profile_facts -> 'operating_system'::text) IS NOT NULL);""",
            "operating system composite index",
        ),
    ]

    for sql, description in composite_indexes:
        execute_sql(session, sql, operation_name=description)

    logger.info("Successfully created composite indexes")


def create_sync_trigger_function(session: Session, logger: Logger):
    """Create the trigger function to sync data between hosts and hosts_new."""
    logger.info("Creating sync trigger function")

    trigger_function_sql = f"""
        CREATE OR REPLACE FUNCTION {INVENTORY_SCHEMA}.sync_hosts_to_new()
        RETURNS TRIGGER AS $$
        BEGIN
            IF (TG_OP = 'INSERT') THEN
                INSERT INTO {INVENTORY_SCHEMA}.hosts_new (
                    org_id, id, account, display_name, ansible_host, created_on, modified_on, facts, tags,
                    tags_alt, system_profile_facts, groups, last_check_in, stale_timestamp, deletion_timestamp,
                    stale_warning_timestamp, reporter, per_reporter_staleness, canonical_facts,
                    canonical_facts_version, is_virtual, insights_id, subscription_manager_id,
                    satellite_id, fqdn, bios_uuid, ip_addresses, mac_addresses, provider_id, provider_type
                )
                VALUES (
                    NEW.org_id, NEW.id, NEW.account, NEW.display_name, NEW.ansible_host, NEW.created_on,
                    NEW.modified_on, NEW.facts, NEW.tags, NEW.tags_alt, NEW.system_profile_facts,
                    NEW.groups, NEW.last_check_in, NEW.stale_timestamp, NEW.deletion_timestamp,
                    NEW.stale_warning_timestamp, NEW.reporter, NEW.per_reporter_staleness,
                    NEW.canonical_facts,
                    (NEW.canonical_facts ->> 'canonical_facts_version')::integer,
                    (NEW.canonical_facts ->> 'is_virtual')::boolean,
                    NEW.canonical_facts ->> 'insights_id',
                    NEW.canonical_facts ->> 'subscription_manager_id',
                    NEW.canonical_facts ->> 'satellite_id',
                    NEW.canonical_facts ->> 'fqdn',
                    NEW.canonical_facts ->> 'bios_uuid',
                    NEW.canonical_facts -> 'ip_addresses',
                    NEW.canonical_facts -> 'mac_addresses',
                    NEW.canonical_facts ->> 'provider_id',
                    NEW.canonical_facts ->> 'provider_type'
                );
                RETURN NEW;

            ELSIF (TG_OP = 'UPDATE') THEN
                UPDATE {INVENTORY_SCHEMA}.hosts_new SET
                    account = NEW.account,
                    display_name = NEW.display_name,
                    ansible_host = NEW.ansible_host,
                    created_on = NEW.created_on,
                    modified_on = NEW.modified_on,
                    facts = NEW.facts,
                    tags = NEW.tags,
                    tags_alt = NEW.tags_alt,
                    system_profile_facts = NEW.system_profile_facts,
                    groups = NEW.groups,
                    last_check_in = NEW.last_check_in,
                    stale_timestamp = NEW.stale_timestamp,
                    deletion_timestamp = NEW.deletion_timestamp,
                    stale_warning_timestamp = NEW.stale_warning_timestamp,
                    reporter = NEW.reporter,
                    per_reporter_staleness = NEW.per_reporter_staleness,
                    canonical_facts = NEW.canonical_facts,
                    canonical_facts_version = (NEW.canonical_facts ->> 'canonical_facts_version')::integer,
                    is_virtual = (NEW.canonical_facts ->> 'is_virtual')::boolean,
                    insights_id = NEW.canonical_facts ->> 'insights_id',
                    subscription_manager_id = NEW.canonical_facts ->> 'subscription_manager_id',
                    satellite_id = NEW.canonical_facts ->> 'satellite_id',
                    fqdn = NEW.canonical_facts ->> 'fqdn',
                    bios_uuid = NEW.canonical_facts ->> 'bios_uuid',
                    ip_addresses = NEW.canonical_facts -> 'ip_addresses',
                    mac_addresses = NEW.canonical_facts -> 'mac_addresses',
                    provider_id = NEW.canonical_facts ->> 'provider_id',
                    provider_type = NEW.canonical_facts ->> 'provider_type'
                WHERE id = NEW.id AND org_id = NEW.org_id;
                RETURN NEW;

            ELSIF (TG_OP = 'DELETE') THEN
                DELETE FROM {INVENTORY_SCHEMA}.hosts_new WHERE id = OLD.id AND org_id = OLD.org_id;
                RETURN OLD;
            END IF;

            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """

    execute_sql(session, trigger_function_sql, operation_name="sync trigger function creation")
    logger.info("Successfully created sync trigger function")


def create_sync_trigger(session: Session, logger: Logger):
    """Create the trigger that calls the sync function."""
    logger.info("Creating sync trigger")

    trigger_sql = f"""
        CREATE TRIGGER hosts_sync_trigger
        AFTER INSERT OR UPDATE OR DELETE ON {INVENTORY_SCHEMA}.hosts
        FOR EACH ROW EXECUTE FUNCTION {INVENTORY_SCHEMA}.sync_hosts_to_new();
    """

    execute_sql(session, trigger_sql, operation_name="sync trigger creation")
    logger.info("Successfully created sync trigger")


def run(logger: Logger, session: Session, application: FlaskApp):
    """Main execution function."""
    with application.app.app_context():
        try:
            # Validate inputs first
            validate_inputs()

            with session_guard(session):
                logger.info(f"Starting hosts table partitioning with {NUM_PARTITIONS} partitions")

                # Create table structure
                create_hosts_new_table(session, logger)

                # Create partitions
                create_partitions(session, logger)

                # Create indexes in logical groups
                create_essential_indexes(session, logger)
                create_jsonb_indexes(session, logger)
                create_functional_indexes(session, logger)
                create_composite_indexes(session, logger)

                # Create sync mechanism
                create_sync_trigger_function(session, logger)
                create_sync_trigger(session, logger)

                logger.info("Successfully completed hosts table partitioning setup")

        except Exception as e:
            logger.error(f"Failed to complete hosts table partitioning: {str(e)}")
            raise


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)
    job_type = "Hosts Table Partitioning"
    sys.excepthook = partial(excepthook, logger, job_type)

    config, session, _, _, _, application = job_setup(tuple(), PROMETHEUS_JOB)
    if config.bypass_db_refactoring_jobs:
        logger.info("bypass_db_refactoring_jobs was set to True; exiting.")
        sys.exit(0)
    else:
        run(logger, session, application)

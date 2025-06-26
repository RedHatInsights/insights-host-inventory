#!/usr/bin/python
# ruff: noqa: E501
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

PROMETHEUS_JOB = "hosts-partitioned-table-data-sync"
LOGGER_NAME = "hosts_partitioned_table_data_sync"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB

INVENTORY_SCHEMA = "hbi"

"""
This job creates a trigger to synchronize data from the hosts table to the hosts_new table.
"""


def execute_sql(session: Session, sql_template: str, operation_name: str = ""):
    """Execute SQL with proper error handling and logging."""
    try:
        session.execute(text(sql_template))
    except Exception as e:
        raise RuntimeError(f"Failed to execute {operation_name}: {str(e)}") from e


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
                    COALESCE((NEW.canonical_facts->>'insights_id')::uuid, '00000000-0000-0000-0000-000000000000'),
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
                    insights_id = COALESCE((NEW.canonical_facts->>'insights_id')::uuid, '00000000-0000-0000-0000-000000000000'),
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
        with session_guard(session):
            create_sync_trigger_function(session, logger)
            create_sync_trigger(session, logger)


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)
    job_type = "Hosts partitioned table synchronizer"
    sys.excepthook = partial(excepthook, logger, job_type)

    config, session, _, _, _, application = job_setup((), PROMETHEUS_JOB)
    if config.bypass_db_refactoring_jobs:
        logger.info("bypass_db_refactoring_jobs was set to True; exiting.")
        sys.exit(0)
    else:
        run(logger, session, application)

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
from app.models.constants import INVENTORY_SCHEMA
from jobs.common import excepthook
from jobs.common import job_setup
from lib.db import session_guard

PROMETHEUS_JOB = "hosts-partitioned-table-data-sync"
LOGGER_NAME = "hosts_partitioned_table_data_sync"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB

"""
This job creates a trigger to synchronize data from the hosts table to the hosts_new partitioned table
and the hosts_groups_new partitioned table
"""


def execute_sql(session: Session, sql_template: str, operation_name: str = ""):
    """Execute SQL with proper error handling and logging."""
    try:
        session.execute(text(sql_template))
    except Exception as e:
        raise RuntimeError(f"Failed to execute {operation_name}: {str(e)}") from e


def create_sync_trigger_function(session: Session, logger: Logger):
    """Create the trigger function to sync data between hosts, hosts_new and hosts_groups_new tables"""
    logger.info("Creating sync trigger function")

    # This trigger function that uses an UPSERT pattern
    # to guarantee data consistency and handle race conditions.
    trigger_function_sql = f"""
        CREATE OR REPLACE FUNCTION {INVENTORY_SCHEMA}.sync_hosts_to_new()
        RETURNS TRIGGER AS $$
        BEGIN
            IF (TG_OP = 'DELETE') THEN
                -- For DELETE, must delete from child table first to respect foreign keys.
                DELETE FROM {INVENTORY_SCHEMA}.hosts_groups_new WHERE host_id = OLD.id AND org_id = OLD.org_id;
                -- Then delete from parent table.
                DELETE FROM {INVENTORY_SCHEMA}.hosts_new WHERE id = OLD.id AND org_id = OLD.org_id;
            ELSE
                -- For INSERT or UPDATE, perform a single, atomic UPSERT on the parent table.
                -- This handles both cases correctly and prevents the race condition.
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
                )
                ON CONFLICT (org_id, id) DO UPDATE SET
                    account = EXCLUDED.account,
                    display_name = EXCLUDED.display_name,
                    ansible_host = EXCLUDED.ansible_host,
                    created_on = EXCLUDED.created_on,
                    modified_on = EXCLUDED.modified_on,
                    facts = EXCLUDED.facts,
                    tags = EXCLUDED.tags,
                    tags_alt = EXCLUDED.tags_alt,
                    system_profile_facts = EXCLUDED.system_profile_facts,
                    groups = EXCLUDED.groups,
                    last_check_in = EXCLUDED.last_check_in,
                    stale_timestamp = EXCLUDED.stale_timestamp,
                    deletion_timestamp = EXCLUDED.deletion_timestamp,
                    stale_warning_timestamp = EXCLUDED.stale_warning_timestamp,
                    reporter = EXCLUDED.reporter,
                    per_reporter_staleness = EXCLUDED.per_reporter_staleness,
                    canonical_facts = EXCLUDED.canonical_facts,
                    canonical_facts_version = EXCLUDED.canonical_facts_version,
                    is_virtual = EXCLUDED.is_virtual,
                    insights_id = EXCLUDED.insights_id,
                    subscription_manager_id = EXCLUDED.subscription_manager_id,
                    satellite_id = EXCLUDED.satellite_id,
                    fqdn = EXCLUDED.fqdn,
                    bios_uuid = EXCLUDED.bios_uuid,
                    ip_addresses = EXCLUDED.ip_addresses,
                    mac_addresses = EXCLUDED.mac_addresses,
                    provider_id = EXCLUDED.provider_id,
                    provider_type = EXCLUDED.provider_type;

                -- After the parent row is guaranteed to exist, sync the child table.
                -- The "delete-then-insert" strategy is still correct here.
                DELETE FROM {INVENTORY_SCHEMA}.hosts_groups_new WHERE host_id = NEW.id AND org_id = NEW.org_id;

                IF NEW.groups IS NOT NULL AND jsonb_typeof(NEW.groups) = 'array' AND jsonb_array_length(NEW.groups) > 0 THEN
                    INSERT INTO {INVENTORY_SCHEMA}.hosts_groups_new (org_id, host_id, group_id)
                    SELECT
                        NEW.org_id,
                        NEW.id,
                        (value ->> 'id')::uuid
                    FROM jsonb_array_elements(NEW.groups);
                END IF;
            END IF;

            -- The return value for an AFTER trigger is ignored.
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
    job_type = "Hosts partitioned tables synchronizer"
    sys.excepthook = partial(excepthook, logger, job_type)

    config, session, _, _, _, application = job_setup((), PROMETHEUS_JOB)

    run(logger, session, application)

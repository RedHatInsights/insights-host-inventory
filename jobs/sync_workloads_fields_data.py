#!/usr/bin/python3
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
from app.models.constants import INVENTORY_SCHEMA
from jobs.common import excepthook
from jobs.common import job_setup

PROMETHEUS_JOB = "sync_workloads_fields_data"
LOGGER_NAME = "sync_workloads_fields_data"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB
SUSPEND_JOB = os.environ.get("SUSPEND_JOB", "true").lower() == "true"


INDEX_DEFINITIONS = {
    # hosts_new indexes
    "idx_hosts_temp_intersystems": "CREATE INDEX IF NOT EXISTS {index_name} ON {schema}.hosts ((system_profile_facts ->> 'intersystems'));",
    "idx_hosts_temp_rhel_ai": "CREATE INDEX IF NOT EXISTS {index_name} ON {schema}.hosts ((system_profile_facts ->> 'rhel_ai'));",
    "idx_hosts_temp_crowdstrike": "CREATE INDEX IF NOT EXISTS {index_name} ON {schema}.hosts ((system_profile_facts -> 'third_party_services' ->> 'crowdstrike'));",
}


def drop_temporary_indexes(session: Session, logger: Logger):
    """Drops the temporary indexes created to speed up the job execution."""
    logger.warning("Dropping all temporary indexes...")
    for index_name in INDEX_DEFINITIONS.keys():
        logger.info(f"  Dropping index: {index_name}")
        session.execute(text(f"DROP INDEX IF EXISTS {INVENTORY_SCHEMA}.{index_name};"))
    session.commit()
    logger.info("All temporary indexes have been dropped.")


def create_temporary_indexes(session: Session, logger: Logger):
    """Creates the temporary indexes to speed up the job execution."""
    logger.info("Creating temporary indexes (this may take a long time)...")
    try:
        for index_name, index_ddl in INDEX_DEFINITIONS.items():
            logger.info(f"  Creating index: {index_name}")
            session.execute(text(index_ddl.format(index_name=index_name, schema=INVENTORY_SCHEMA)))

        logger.info("Committing index creation transaction...")
        session.commit()
        logger.info("All indexes have been created successfully.")
    except Exception:
        logger.error("An error occurred during index creation. Rolling back.")
        session.rollback()
        raise


def sync_spf_workloads_fields(session: Session, logger: Logger):
    """
    Migrates ansible, mssql, crowdstrike, intersystems, rhel_ai, and sap data from the system_profile_facts
    column to the top-level workloads column in both the 'hosts' and 'system_profiles_dynamic' tables
    using set-based SQL operations.
    """
    logger.info("Starting workload data migration for 'hosts' and 'system_profiles_dynamic' tables.")

    # --- SQL Statements for 'hosts' table ---
    sql_update_hosts_ansible = f"""
        UPDATE {INVENTORY_SCHEMA}.hosts
        SET system_profile_facts = system_profile_facts || jsonb_build_object(
            'workloads',
            (COALESCE(system_profile_facts -> 'workloads', '{{}}'::jsonb)) || jsonb_build_object(
                'ansible', jsonb_build_object(
                    'controller_version', system_profile_facts -> 'ansible' -> 'controller_version',
                    'hub_version', system_profile_facts -> 'ansible' -> 'hub_version',
                    'catalog_worker_version', system_profile_facts -> 'ansible' -> 'catalog_worker_version',
                    'sso_version', system_profile_facts -> 'ansible' -> 'sso_version'
                )
            )
        )
        WHERE system_profile_facts ->> 'ansible' IS NOT NULL;
    """

    sql_update_hosts_mssql = f"""
        UPDATE {INVENTORY_SCHEMA}.hosts
        SET system_profile_facts = system_profile_facts || jsonb_build_object(
            'workloads',
            (COALESCE(system_profile_facts -> 'workloads', '{{}}'::jsonb)) || jsonb_build_object(
                'mssql', jsonb_build_object(
                    'version', system_profile_facts -> 'mssql' -> 'version'
                )
            )
        )
        WHERE system_profile_facts ->> 'mssql' IS NOT NULL;
    """

    sql_update_hosts_sap = f"""
        UPDATE {INVENTORY_SCHEMA}.hosts
        SET system_profile_facts = system_profile_facts || jsonb_build_object(
            'workloads',
            (COALESCE(system_profile_facts -> 'workloads', '{{}}'::jsonb)) || jsonb_build_object(
                'sap', jsonb_build_object(
                    'sap_system', TRUE,
                    'sids', COALESCE(system_profile_facts -> 'sap' -> 'sids', '[]'::jsonb),
                    'instance_number', system_profile_facts -> 'sap' -> 'instance_number',
                    'version', system_profile_facts -> 'sap' -> 'version'
                )
            )
        )
        WHERE (system_profile_facts ->> 'sap_system')::boolean IS TRUE;
    """

    sql_update_hosts_intersystems = f"""
        UPDATE {INVENTORY_SCHEMA}.hosts
        SET system_profile_facts = system_profile_facts || jsonb_build_object(
            'workloads',
            (COALESCE(system_profile_facts -> 'workloads', '{{}}'::jsonb)) || jsonb_build_object(
                'intersystems', jsonb_build_object(
                    'is_intersystems', TRUE,
                    'running_instances', system_profile_facts -> 'intersystems' -> 'running_instances'
                )
            )
        )
        WHERE (system_profile_facts -> 'intersystems' ->> 'is_intersystems')::boolean IS TRUE;
    """

    sql_update_hosts_crowdstrike = f"""
        UPDATE {INVENTORY_SCHEMA}.hosts
        SET system_profile_facts = system_profile_facts || jsonb_build_object(
            'workloads',
            (COALESCE(system_profile_facts -> 'workloads', '{{}}'::jsonb)) || jsonb_build_object(
                'crowdstrike', jsonb_build_object(
                    'falcon_aid', system_profile_facts -> 'third_party_services' -> 'crowdstrike' -> 'falcon_aid',
                    'falcon_backend', system_profile_facts -> 'third_party_services' -> 'crowdstrike' -> 'falcon_backend',
                    'falcon_version', system_profile_facts -> 'third_party_services' -> 'crowdstrike' -> 'falcon_version'
                )
            )
        )
        WHERE system_profile_facts -> 'third_party_services' ->> 'crowdstrike' IS NOT NULL;
    """

    sql_update_hosts_rhel_ai = f"""
        UPDATE {INVENTORY_SCHEMA}.hosts
        SET system_profile_facts = system_profile_facts || jsonb_build_object(
            'workloads',
            (COALESCE(system_profile_facts -> 'workloads', '{{}}'::jsonb)) || jsonb_build_object(
                'rhel_ai', jsonb_build_object(
                    'variant', system_profile_facts -> 'rhel_ai' -> 'variant',
                    'rhel_ai_version_id', system_profile_facts -> 'rhel_ai' -> 'rhel_ai_version_id'
                )
            )
        )
        WHERE (system_profile_facts ->> 'rhel_ai') IS NOT NULL;
    """

    # --- SQL Statements for 'system_profiles_dynamic' table ---
    # These queries use UPDATE...FROM to join hosts and update system_profiles_dynamic based on host data.
    # --- SQL Statements for 'system_profiles_dynamic' table ---
    sql_update_dynamic_ansible = f"""
        UPDATE {INVENTORY_SCHEMA}.system_profiles_dynamic spd
        SET workloads = COALESCE(spd.workloads, '{{}}'::jsonb) || jsonb_build_object(
            'ansible',
            jsonb_build_object(
                'controller_version', h.system_profile_facts -> 'ansible' -> 'controller_version',
                'hub_version', h.system_profile_facts -> 'ansible' -> 'hub_version',
                'catalog_worker_version', h.system_profile_facts -> 'ansible' -> 'catalog_worker_version',
                'sso_version', h.system_profile_facts -> 'ansible' -> 'sso_version'
            )
        )
        FROM {INVENTORY_SCHEMA}.hosts h
        WHERE spd.host_id = h.id AND h.system_profile_facts ->> 'ansible' IS NOT NULL;
    """
    sql_update_dynamic_mssql = f"""
        UPDATE {INVENTORY_SCHEMA}.system_profiles_dynamic spd
        SET workloads = COALESCE(spd.workloads, '{{}}'::jsonb) || jsonb_build_object(
            'mssql',
            jsonb_build_object(
                'version', h.system_profile_facts -> 'mssql' -> 'version'
            )
        )
        FROM {INVENTORY_SCHEMA}.hosts h
        WHERE spd.host_id = h.id AND h.system_profile_facts ->> 'mssql' IS NOT NULL;
    """
    sql_update_dynamic_sap = f"""
        UPDATE {INVENTORY_SCHEMA}.system_profiles_dynamic spd
        SET workloads = COALESCE(spd.workloads, '{{}}'::jsonb) || jsonb_build_object(
            'sap',
            jsonb_build_object(
                'sap_system', TRUE,
                'sids', COALESCE(h.system_profile_facts -> 'sap' -> 'sids', '[]'::jsonb),
                'instance_number', h.system_profile_facts -> 'sap' -> 'instance_number',
                'version', h.system_profile_facts -> 'sap' -> 'version'
            )
        )
        FROM {INVENTORY_SCHEMA}.hosts h
        WHERE spd.host_id = h.id AND (h.system_profile_facts ->> 'sap_system')::boolean IS TRUE;
    """
    sql_update_dynamic_intersystems = f"""
        UPDATE {INVENTORY_SCHEMA}.system_profiles_dynamic spd
        SET workloads = COALESCE(spd.workloads, '{{}}'::jsonb) || jsonb_build_object(
            'intersystems',
            jsonb_build_object(
                'is_intersystems', TRUE,
                'running_instances', h.system_profile_facts -> 'intersystems' -> 'running_instances'
            )
        )
        FROM {INVENTORY_SCHEMA}.hosts h
        WHERE spd.host_id = h.id AND h.system_profile_facts -> 'intersystems' ->> 'intersystems' IS NOT NULL;
    """
    sql_update_dynamic_crowdstrike = f"""
        UPDATE {INVENTORY_SCHEMA}.system_profiles_dynamic spd
        SET workloads = COALESCE(spd.workloads, '{{}}'::jsonb) || jsonb_build_object(
            'crowdstrike',
            jsonb_build_object(
                'falcon_aid', h.system_profile_facts -> 'third_party_services' -> 'crowdstrike' -> 'falcon_aid',
                'falcon_backend', h.system_profile_facts -> 'third_party_services' -> 'crowdstrike' -> 'falcon_backend',
                'falcon_version', h.system_profile_facts -> 'third_party_services' -> 'crowdstrike' -> 'falcon_version'
            )
        )
        FROM {INVENTORY_SCHEMA}.hosts h
        WHERE spd.host_id = h.id AND h.system_profile_facts -> 'third_party_services' ->> 'crowdstrike' IS NOT NULL;
    """
    sql_update_dynamic_rhel_ai = f"""
        UPDATE {INVENTORY_SCHEMA}.system_profiles_dynamic spd
        SET workloads = COALESCE(spd.workloads, '{{}}'::jsonb) || jsonb_build_object(
            'rhel_ai',
            jsonb_build_object(
                'variant', h.system_profile_facts -> 'rhel_ai' -> 'variant',
                'rhel_ai_version_id', h.system_profile_facts -> 'rhel_ai' -> 'rhel_ai_version_id'
            )
        )
        FROM {INVENTORY_SCHEMA}.hosts h
        WHERE spd.host_id = h.id AND h.system_profile_facts ->> 'rhel_ai' IS NOT NULL;
    """

    try:
        # --- Process 'hosts' table ---
        logger.info("Updating 'hosts' table...")

        result_ansible = session.execute(text(sql_update_hosts_ansible))
        logger.info(f"  Updated {result_ansible.rowcount} hosts with 'ansible' workloads.")

        result_mssql = session.execute(text(sql_update_hosts_mssql))
        logger.info(f"  Updated {result_mssql.rowcount} hosts with 'mssql' workloads.")

        result_sap = session.execute(text(sql_update_hosts_sap))
        logger.info(f"  Updated {result_sap.rowcount} hosts with 'sap_system' workloads.")

        result_intersystems = session.execute(text(sql_update_hosts_intersystems))
        logger.info(f"  Updated {result_intersystems.rowcount} hosts with 'intersystems' workloads.")

        result_crowdstrike = session.execute(text(sql_update_hosts_crowdstrike))
        logger.info(f"  Updated {result_crowdstrike.rowcount} hosts with 'crowdstrike' workloads.")

        result_rhel_ai = session.execute(text(sql_update_hosts_rhel_ai))
        logger.info(f"  Updated {result_rhel_ai.rowcount} hosts with 'rhel_ai' workloads.")

        logger.info("'hosts' table update complete.")

        # --- Process 'system_profiles_dynamic' table ---
        logger.info("Updating 'system_profiles_dynamic' table...")

        result_dyn_ansible = session.execute(text(sql_update_dynamic_ansible))
        logger.info(f"  Updated {result_dyn_ansible.rowcount} dynamic profiles with 'ansible' workloads.")

        result_dyn_mssql = session.execute(text(sql_update_dynamic_mssql))
        logger.info(f"  Updated {result_dyn_mssql.rowcount} dynamic profiles with 'mssql' workloads.")

        result_dyn_sap = session.execute(text(sql_update_dynamic_sap))
        logger.info(f"  Updated {result_dyn_sap.rowcount} dynamic profiles with 'sap_system' workloads.")

        result_dyn_intersystems = session.execute(text(sql_update_dynamic_intersystems))
        logger.info(f"  Updated {result_dyn_intersystems.rowcount} dynamic profiles with 'intersystems' workloads.")

        result_dyn_crowdstrike = session.execute(text(sql_update_dynamic_crowdstrike))
        logger.info(f"  Updated {result_dyn_crowdstrike.rowcount} dynamic profiles with 'crowdstrike' workloads.")

        result_dyn_rhel_ai = session.execute(text(sql_update_dynamic_rhel_ai))
        logger.info(f"  Updated {result_dyn_rhel_ai.rowcount} dynamic profiles with 'rhel_ai' workloads.")

        logger.info("'system_profiles_dynamic' table update complete.")
        session.commit()
        logger.info("Successfully committed all workload migrations for both tables.")
    except Exception:
        logger.exception("A critical error occurred during the workload data migration. Rolling back transaction.")
        session.rollback()
        raise
    finally:
        logger.info("Closing database session.")
        session.close()


def run(logger: Logger, session: Session, application: FlaskApp):
    """Main execution function."""
    try:
        with application.app.app_context():
            create_temporary_indexes(session, logger)
            sync_spf_workloads_fields(session, logger)
            drop_temporary_indexes(session, logger)
    except Exception:
        logger.exception("A critical error occurred during the data copy job.")
        raise
    finally:
        logger.info("Closing database session.")
        session.close()


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)

    if SUSPEND_JOB:
        logger.info("SUSPEND_JOB is set to true; exiting job.")
        sys.exit(0)

    job_type = "Sync workloads fields data"
    sys.excepthook = partial(excepthook, logger, job_type)

    _, session, _, _, _, application = job_setup((), PROMETHEUS_JOB)

    run(logger, session, application)

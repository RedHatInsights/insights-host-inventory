#!/usr/bin/python3
# ruff: noqa: E501
import argparse
import os
import sys
import time
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

PROMETHEUS_JOB = "system-profile-tables-migration-data-copy"
LOGGER_NAME = "system_profile_tables_migration_data_copy"
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB

INDEX_DEFINITIONS = {
    "idx_system_profiles_static_replica_identity": "CREATE UNIQUE INDEX {index_name} ON {schema}.system_profiles_static (org_id, host_id, insights_id);",
    "idx_system_profiles_dynamic_replica_identity": "CREATE UNIQUE INDEX {index_name} ON {schema}.system_profiles_dynamic (org_id, host_id, insights_id);",
    "idx_system_profiles_static_bootc_status": "CREATE INDEX {index_name} ON {schema}.system_profiles_static (bootc_status);",
    "idx_system_profiles_static_host_id": "CREATE INDEX {index_name} ON {schema}.system_profiles_static (host_id);",
    "idx_system_profiles_static_host_type": "CREATE INDEX {index_name} ON {schema}.system_profiles_static (host_type);",
    "idx_system_profiles_static_operating_system_multi": """
        CREATE INDEX {index_name} ON {schema}.system_profiles_static (
            ((operating_system ->> 'name'::text)),
            ((operating_system ->> 'major'::text)::integer),
            ((operating_system ->> 'minor'::text)::integer),
            org_id
        ) WHERE operating_system IS NOT NULL;
    """,
    "idx_system_profiles_static_org_id": "CREATE INDEX {index_name} ON {schema}.system_profiles_static (org_id);",
    "idx_system_profiles_static_rhc_client_id": "CREATE INDEX {index_name} ON {schema}.system_profiles_static (rhc_client_id);",
    "idx_system_profiles_static_system_update_method": "CREATE INDEX {index_name} ON {schema}.system_profiles_static (system_update_method);",
    "idx_system_profiles_dynamic_workloads_gin": "CREATE INDEX {index_name} ON {schema}.system_profiles_dynamic USING gin (workloads);",
}


def parse_partitions(partition_str: str) -> list[int]:
    """Parses a string like "0-7,12,15" into a list of integers."""
    partitions: set[int] = set()
    parts = partition_str.split(",")
    for part in parts:
        if "-" in part:
            start, end = map(int, part.split("-"))
            partitions.update(range(start, end + 1))
        else:
            partitions.add(int(part))
    return sorted(list(partitions))


def drop_columns(session: Session, logger: Logger):
    """Drops the intersystems and rhel_ai columns from the system_profiles_static table."""
    logger.warning("Dropping 'intersystems' and 'rhel_ai' columns from system_profiles_static...")
    session.execute(
        text(
            f"""
            ALTER TABLE {INVENTORY_SCHEMA}.system_profiles_static
            DROP COLUMN IF EXISTS intersystems,
            DROP COLUMN IF EXISTS rhel_ai;
        """
        )
    )
    session.commit()
    logger.info("Columns have been dropped successfully.")


def drop_indexes(session: Session, logger: Logger):
    """Drops all non-primary key indexes from the target tables to speed up inserts."""
    logger.warning("Dropping all non-PK indexes from target tables to optimize data copy...")
    for index_name in INDEX_DEFINITIONS.keys():
        logger.info(f"  Dropping index: {index_name}")
        session.execute(text(f"DROP INDEX IF EXISTS {INVENTORY_SCHEMA}.{index_name};"))
    session.commit()
    logger.info("All non-PK indexes have been dropped.")


def recreate_indexes(session: Session, logger: Logger):
    """Recreates all indexes using a data-driven approach after the data copy is complete."""
    logger.info("Data copy finished. Recreating all indexes (this may take a long time)...")
    try:
        for index_name, index_ddl in INDEX_DEFINITIONS.items():
            logger.info(f"  Recreating index: {index_name}")
            session.execute(text(index_ddl.format(index_name=index_name, schema=INVENTORY_SCHEMA)))

        logger.info("Committing index creation transaction...")
        session.commit()
        logger.info("All indexes have been recreated successfully.")
    except Exception:
        logger.error("An error occurred during index recreation. Rolling back.")
        session.rollback()
        raise


def copy_profile_data_in_batches(session: Session, logger: Logger, partitions_to_process: list[int]):
    """
    Copies data from the hosts partitions into the two new partitioned tables,
    creating records only when relevant data exists.
    """
    # Define the keys that correspond to columns in each target table.
    dynamic_keys = [
        "captured_date",
        "running_processes",
        "last_boot_time",
        "installed_packages",
        "installed_products",
        "network_interfaces",
        "cpu_flags",
        "insights_egg_version",
        "kernel_modules",
        "system_memory_bytes",
        "systemd",
        "workloads",
    ]

    static_keys = [
        "arch",
        "basearch",
        "bios_release_date",
        "bios_vendor",
        "bios_version",
        "bootc_status",
        "cloud_provider",
        "conversions",
        "cores_per_socket",
        "cpu_model",
        "disk_devices",
        "dnf_modules",
        "enabled_services",
        "gpg_pubkeys",
        "greenboot_fallback_detected",
        "greenboot_status",
        "host_type",
        "image_builder",
        "infrastructure_type",
        "infrastructure_vendor",
        "insights_client_version",
        "installed_packages_delta",
        "installed_services",
        "is_marketplace",
        "katello_agent_running",
        "number_of_cpus",
        "number_of_sockets",
        "operating_system",
        "os_kernel_version",
        "os_release",
        "owner_id",
        "public_dns",
        "public_ipv4_addresses",
        "releasever",
        "rhc_client_id",
        "rhc_config_state",
        "rhsm",
        "rpm_ostree_deployments",
        "satellite_managed",
        "selinux_config_file",
        "selinux_current_mode",
        "subscription_auto_attach",
        "subscription_status",
        "system_purpose",
        "system_update_method",
        "third_party_services",
        "threads_per_core",
        "tuned_profile",
        "virtual_host_uuid",
        "yum_repos",
    ]

    # Format the key lists for use in the SQL ARRAY constructor.
    dynamic_keys_sql_array = "ARRAY['" + "','".join(dynamic_keys) + "']"
    static_keys_sql_array = "ARRAY['" + "','".join(static_keys) + "']"

    batch_size = int(os.getenv("SP_TABLES_MIGRATION_BATCH_SIZE", 10000))
    grand_total_rows_copied = 0

    logger.info(f"Starting data migration for partitions: {partitions_to_process} with batch size {batch_size}.")

    for partition_num in partitions_to_process:
        partition_table = f"{INVENTORY_SCHEMA}.hosts_p{partition_num}"
        logger.info(f"--- Starting processing for partition: {partition_table} ---")

        last_modified_on = "9999-12-31 23:59:59+00"
        last_id = "ffffffff-ffff-ffff-ffff-ffffffffffff"
        partition_total_rows = 0

        while True:
            batch_start_time = time.perf_counter()
            logger.info(
                f"[{partition_table}] Fetching next batch of host IDs modified before: {last_modified_on} - {last_id}"
            )

            batch_cursors = session.execute(
                text(
                    f"""
                    SELECT id, modified_on FROM {partition_table}
                    WHERE (modified_on, id) < (:last_modified_on, :last_id)
                    ORDER BY modified_on DESC, id DESC
                    LIMIT :batch_size;
                    """
                ),
                {"last_modified_on": last_modified_on, "last_id": last_id, "batch_size": batch_size},
            ).fetchall()

            if not batch_cursors:
                logger.info(f"[{partition_table}] No more hosts to process. Partition migration complete.")
                break

            id_list = [row.id for row in batch_cursors]
            logger.info(f"[{partition_table}] Fetched {len(id_list)} host IDs. Now processing the batch...")

            combined_sql = f"""
                WITH batch AS (
                    SELECT id, org_id, insights_id, system_profile_facts
                    FROM {partition_table}
                    WHERE id = ANY(:id_list)
                ),
                dynamic_insert AS (
                    INSERT INTO {INVENTORY_SCHEMA}.system_profiles_dynamic (
                        org_id, host_id, insights_id, captured_date, running_processes, last_boot_time, installed_packages,
                        installed_products, network_interfaces, cpu_flags, insights_egg_version, kernel_modules,
                        system_memory_bytes, systemd, workloads
                    )
                    SELECT
                        b.org_id, b.id, b.insights_id,
                        (b.system_profile_facts ->> 'captured_date')::timestamptz,
                        (SELECT array_agg(value) FROM jsonb_array_elements_text(b.system_profile_facts -> 'running_processes')),
                        (b.system_profile_facts ->> 'last_boot_time')::timestamptz,
                        (SELECT array_agg(value) FROM jsonb_array_elements_text(b.system_profile_facts -> 'installed_packages')),
                        b.system_profile_facts -> 'installed_products',
                        b.system_profile_facts -> 'network_interfaces',
                        (SELECT array_agg(value) FROM jsonb_array_elements_text(b.system_profile_facts -> 'cpu_flags')),
                        b.system_profile_facts ->> 'insights_egg_version',
                        (SELECT array_agg(value) FROM jsonb_array_elements_text(b.system_profile_facts -> 'kernel_modules')),
                        (b.system_profile_facts ->> 'system_memory_bytes')::bigint,
                        b.system_profile_facts -> 'systemd',
                        b.system_profile_facts -> 'workloads'
                    FROM batch b
                    WHERE b.system_profile_facts ?| {dynamic_keys_sql_array}
                    ON CONFLICT (org_id, host_id) DO NOTHING
                )
                INSERT INTO {INVENTORY_SCHEMA}.system_profiles_static (
                    org_id, host_id, insights_id, arch, basearch, bios_release_date, bios_vendor, bios_version,
                    bootc_status, cloud_provider, conversions, cores_per_socket, cpu_model, disk_devices, dnf_modules,
                    enabled_services, gpg_pubkeys, greenboot_fallback_detected, greenboot_status, host_type,
                    image_builder, infrastructure_type, infrastructure_vendor, insights_client_version,
                    installed_packages_delta,installed_services, is_marketplace, katello_agent_running,
                    number_of_cpus, number_of_sockets, operating_system, os_kernel_version, os_release, owner_id,
                    public_dns, public_ipv4_addresses, releasever, rhc_client_id, rhc_config_state, rhsm,
                    rpm_ostree_deployments, satellite_managed, selinux_config_file, selinux_current_mode,
                    subscription_auto_attach, subscription_status, system_purpose, system_update_method,
                    third_party_services, threads_per_core, tuned_profile, virtual_host_uuid, yum_repos
                )
                SELECT
                    b.org_id, b.id, b.insights_id,
                    b.system_profile_facts ->> 'arch', b.system_profile_facts ->> 'basearch',
                    b.system_profile_facts ->> 'bios_release_date', b.system_profile_facts ->> 'bios_vendor',
                    b.system_profile_facts ->> 'bios_version', b.system_profile_facts -> 'bootc_status',
                    b.system_profile_facts ->> 'cloud_provider', b.system_profile_facts -> 'conversions',
                    (b.system_profile_facts ->> 'cores_per_socket')::integer, b.system_profile_facts ->> 'cpu_model',
                    (SELECT array_agg(value) FROM jsonb_array_elements(b.system_profile_facts -> 'disk_devices')),
                    (SELECT array_agg(value) FROM jsonb_array_elements(b.system_profile_facts -> 'dnf_modules')),
                    (SELECT array_agg(value) FROM jsonb_array_elements_text(b.system_profile_facts -> 'enabled_services')),
                    (SELECT array_agg(value) FROM jsonb_array_elements_text(b.system_profile_facts -> 'gpg_pubkeys')),
                    (b.system_profile_facts ->> 'greenboot_fallback_detected')::boolean,
                    b.system_profile_facts ->> 'greenboot_status', b.system_profile_facts ->> 'host_type',
                    b.system_profile_facts -> 'image_builder', b.system_profile_facts ->> 'infrastructure_type',
                    b.system_profile_facts ->> 'infrastructure_vendor', b.system_profile_facts ->> 'insights_client_version',
                    (SELECT array_agg(value) FROM jsonb_array_elements_text(b.system_profile_facts -> 'installed_packages_delta')),
                    (SELECT array_agg(value) FROM jsonb_array_elements_text(b.system_profile_facts -> 'installed_services')),
                    (b.system_profile_facts ->> 'is_marketplace')::boolean,
                    (b.system_profile_facts ->> 'katello_agent_running')::boolean,
                    (b.system_profile_facts ->> 'number_of_cpus')::integer,
                    (b.system_profile_facts ->> 'number_of_sockets')::integer, b.system_profile_facts -> 'operating_system',
                    b.system_profile_facts ->> 'os_kernel_version', b.system_profile_facts ->> 'os_release',
                    (b.system_profile_facts ->> 'owner_id')::uuid,
                    (SELECT array_agg(value) FROM jsonb_array_elements_text(b.system_profile_facts -> 'public_dns')),
                    (SELECT array_agg(value) FROM jsonb_array_elements_text(b.system_profile_facts -> 'public_ipv4_addresses')),
                    b.system_profile_facts ->> 'releasever', (b.system_profile_facts ->> 'rhc_client_id')::uuid,
                    (b.system_profile_facts ->> 'rhc_config_state')::uuid,
                    b.system_profile_facts -> 'rhsm',
                    (SELECT array_agg(value) FROM jsonb_array_elements(b.system_profile_facts -> 'rpm_ostree_deployments')),
                    (b.system_profile_facts ->> 'satellite_managed')::boolean,
                    b.system_profile_facts ->> 'selinux_config_file', b.system_profile_facts ->> 'selinux_current_mode',
                    b.system_profile_facts ->> 'subscription_auto_attach', b.system_profile_facts ->> 'subscription_status',
                    b.system_profile_facts -> 'system_purpose', b.system_profile_facts ->> 'system_update_method',
                    b.system_profile_facts -> 'third_party_services',
                    (b.system_profile_facts ->> 'threads_per_core')::integer, b.system_profile_facts ->> 'tuned_profile',
                    (b.system_profile_facts ->> 'virtual_host_uuid')::uuid,
                    (SELECT array_agg(value) FROM jsonb_array_elements(b.system_profile_facts -> 'yum_repos'))
                FROM batch b
                WHERE b.system_profile_facts ?| {static_keys_sql_array}
                ON CONFLICT (org_id, host_id) DO NOTHING;
            """
            session.execute(text(combined_sql), {"id_list": id_list})

            last_row = batch_cursors[-1]
            last_id = last_row.id
            last_modified_on = last_row.modified_on

            partition_total_rows += len(batch_cursors)
            batch_duration = time.perf_counter() - batch_start_time
            logger.info(
                f"[{partition_table}] Batch complete in {batch_duration:.2f}s. "
                f"Processed {len(batch_cursors)} rows. "
                f"Total rows for this partition: {partition_total_rows}. "
                f"Next batch starts before: {last_modified_on}"
            )
            session.commit()
        grand_total_rows_copied += partition_total_rows

    logger.info(f"Successfully finished copying all data. Total rows processed: {grand_total_rows_copied}.")


def run(logger: Logger, session: Session, application: FlaskApp, mode: str, partitions: list[int] | None):
    """Main execution function."""
    try:
        with application.app.app_context():
            if mode == "prepare":
                drop_columns(session, logger)
                drop_indexes(session, logger)
                logger.info("Preparation complete. You can now run the migration jobs in parallel.")
            elif mode == "migrate":
                if not partitions:
                    raise ValueError("--partitions is required for 'migrate' mode.")
                copy_profile_data_in_batches(session, logger, partitions)
            elif mode == "finalize":
                recreate_indexes(session, logger)
                logger.info("Finalization complete. All indexes have been recreated.")
            else:
                raise ValueError(f"Invalid mode: {mode}")
    except Exception:
        logger.exception(f"A critical error occurred during the system profile data copy job (mode: {mode}).")
        raise
    finally:
        logger.info("Closing database session.")
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        required=True,
        choices=["prepare", "migrate", "finalize"],
        help="The stage of the migration to run.",
    )
    parser.add_argument(
        "--partitions",
        help="A comma-separated list or range of partitions to process (e.g., '0-7,12,15'). Required for 'migrate' mode.",
    )
    parser.add_argument(
        "--suspend",
        choices=["true", "false"],
        default="true",
        help="Whether to suspend the job from running (true/false). Default is true.",
    )
    args = parser.parse_args()

    logger = get_logger(LOGGER_NAME)

    if args.suspend.lower() == "true":
        logger.info(f"SUSPEND flag is set to true for job in mode '{args.mode}'; exiting.")
        sys.exit(0)

    job_type = f"System Profile partitioned tables data copy (mode: {args.mode})"
    sys.excepthook = partial(excepthook, logger, job_type)

    _, session, _, _, _, application = job_setup((), PROMETHEUS_JOB)

    partitions_to_process = None
    if args.partitions:
        partitions_to_process = parse_partitions(args.partitions)

    run(logger, session, application, args.mode, partitions_to_process)

"""system_profiles_data_migration
Revision ID: 7580b7bc0d00
Revises: d705de909597
Create Date: 2025-07-31 08:21:15.437099
"""

import os

from alembic import op

from app.models.constants import INVENTORY_SCHEMA

# revision identifiers, used by Alembic.
revision = "7580b7bc0d00"
down_revision = "3b60b7daf0f2"
branch_labels = None
depends_on = None

"""
This migration copies and extracts data from the 'hosts.system_profile_facts' column
into the new partitioned tables ('system_profiles_dynamic' and 'system_profiles_static').
It assumes the new `system_profiles_static` and `system_profiles_dynamic` tables were
created in the prior migration (3b60b7daf0f2).

This script's behavior is conditional based on the `MIGRATION_MODE` environment variable:

- **automated:** Performs the complete data copy from the 'hosts.system_profile_facts' column
into the new partitioned tables ('system_profiles_dynamic' and 'system_profiles_static').
This mode is intended for automated setups like local development, ephemeral and on-premise environments.

- **managed:** Skips all data operations. It only "stamps" this migration as complete.
This mode is intended for stage and production environments where the data migration is
performed via controlled, external script.
"""


def upgrade():
    migration_mode = os.environ.get("MIGRATION_MODE", "automated").lower()

    # For 'automated' mode (local, ephemeral, on-premise), this script performs the full data copy.
    # For 'managed' mode, this logic is handled by external script (system_profile_tables_migration_data_copy.py)
    # running as Openshift jobs and this migration only stamps the version.
    if migration_mode == "automated":
        op.execute(f"""
            INSERT INTO {INVENTORY_SCHEMA}.system_profiles_dynamic (
                org_id, host_id, insights_id, captured_date, running_processes, last_boot_time, installed_packages,
                installed_products, network_interfaces, cpu_flags, insights_egg_version, kernel_modules,
                system_memory_bytes, systemd, workloads
            )
            SELECT
                h.org_id,
                h.id,
                h.insights_id,
                (h.system_profile_facts ->> 'captured_date')::timestamptz,
                (SELECT array_agg(value)
                    FROM jsonb_array_elements_text(h.system_profile_facts -> 'running_processes')),
                (h.system_profile_facts ->> 'last_boot_time')::timestamptz,
                (SELECT array_agg(value)
                    FROM jsonb_array_elements_text(h.system_profile_facts -> 'installed_packages')),
                h.system_profile_facts -> 'installed_products',
                h.system_profile_facts -> 'network_interfaces',
                (SELECT array_agg(value) FROM jsonb_array_elements_text(h.system_profile_facts -> 'cpu_flags')),
                h.system_profile_facts ->> 'insights_egg_version',
                (SELECT array_agg(value)
                    FROM jsonb_array_elements_text(h.system_profile_facts -> 'kernel_modules')),
                (h.system_profile_facts ->> 'system_memory_bytes')::bigint,
                h.system_profile_facts -> 'systemd',
                h.system_profile_facts -> 'workloads'
            FROM {INVENTORY_SCHEMA}.hosts h
            ON CONFLICT (org_id, host_id) DO NOTHING;
        """)

        op.execute(f"""
            INSERT INTO {INVENTORY_SCHEMA}.system_profiles_static (
                org_id, host_id, insights_id, arch, basearch, bios_release_date, bios_vendor, bios_version,
                bootc_status, cloud_provider, conversions, cores_per_socket, cpu_model, disk_devices, dnf_modules,
                enabled_services, gpg_pubkeys, greenboot_fallback_detected, greenboot_status, host_type,
                image_builder, infrastructure_type, infrastructure_vendor, insights_client_version,
                installed_packages_delta,installed_services, intersystems, is_marketplace, katello_agent_running,
                number_of_cpus, number_of_sockets, operating_system, os_kernel_version, os_release, owner_id,
                public_dns, public_ipv4_addresses, releasever, rhc_client_id, rhc_config_state, rhel_ai, rhsm,
                rpm_ostree_deployments, satellite_managed, selinux_config_file, selinux_current_mode,
                subscription_auto_attach, subscription_status, system_purpose, system_update_method,
                third_party_services, threads_per_core, tuned_profile, virtual_host_uuid, yum_repos
            )
            SELECT
                h.org_id,
                h.id,
                h.insights_id,
                h.system_profile_facts ->> 'arch',
                h.system_profile_facts ->> 'basearch',
                h.system_profile_facts ->> 'bios_release_date',
                h.system_profile_facts ->> 'bios_vendor',
                h.system_profile_facts ->> 'bios_version',
                h.system_profile_facts -> 'bootc_status',
                h.system_profile_facts ->> 'cloud_provider',
                h.system_profile_facts -> 'conversions',
                (h.system_profile_facts ->> 'cores_per_socket')::integer,
                h.system_profile_facts ->> 'cpu_model',
                (SELECT array_agg(value) FROM jsonb_array_elements(h.system_profile_facts -> 'disk_devices')),
                (SELECT array_agg(value) FROM jsonb_array_elements(h.system_profile_facts -> 'dnf_modules')),
                (SELECT array_agg(value) FROM jsonb_array_elements_text(h.system_profile_facts -> 'enabled_services')),
                (SELECT array_agg(value) FROM jsonb_array_elements_text(h.system_profile_facts -> 'gpg_pubkeys')),
                (h.system_profile_facts ->> 'greenboot_fallback_detected')::boolean,
                h.system_profile_facts ->> 'greenboot_status',
                h.system_profile_facts ->> 'host_type',
                h.system_profile_facts -> 'image_builder',
                h.system_profile_facts ->> 'infrastructure_type',
                h.system_profile_facts ->> 'infrastructure_vendor',
                h.system_profile_facts ->> 'insights_client_version',
                (SELECT array_agg(value)
                    FROM jsonb_array_elements_text(h.system_profile_facts -> 'installed_packages_delta')),
                (SELECT array_agg(value)
                    FROM jsonb_array_elements_text(h.system_profile_facts -> 'installed_services')),
                h.system_profile_facts -> 'intersystems',
                (h.system_profile_facts ->> 'is_marketplace')::boolean,
                (h.system_profile_facts ->> 'katello_agent_running')::boolean,
                (h.system_profile_facts ->> 'number_of_cpus')::integer,
                (h.system_profile_facts ->> 'number_of_sockets')::integer,
                h.system_profile_facts -> 'operating_system',
                h.system_profile_facts ->> 'os_kernel_version',
                h.system_profile_facts ->> 'os_release',
                (h.system_profile_facts ->> 'owner_id')::uuid,
                (SELECT array_agg(value) FROM jsonb_array_elements_text(h.system_profile_facts -> 'public_dns')),
                (SELECT array_agg(value)
                    FROM jsonb_array_elements_text(h.system_profile_facts -> 'public_ipv4_addresses')),
                h.system_profile_facts ->> 'releasever',
                (h.system_profile_facts ->> 'rhc_client_id')::uuid,
                (h.system_profile_facts ->> 'rhc_config_state')::uuid,
                h.system_profile_facts -> 'rhel_ai',
                h.system_profile_facts -> 'rhsm',
                (SELECT array_agg(value)
                    FROM jsonb_array_elements(h.system_profile_facts -> 'rpm_ostree_deployments')),
                (h.system_profile_facts ->> 'satellite_managed')::boolean,
                h.system_profile_facts ->> 'selinux_config_file',
                h.system_profile_facts ->> 'selinux_current_mode',
                h.system_profile_facts ->> 'subscription_auto_attach',
                h.system_profile_facts ->> 'subscription_status',
                h.system_profile_facts -> 'system_purpose',
                h.system_profile_facts ->> 'system_update_method',
                h.system_profile_facts -> 'third_party_services',
                (h.system_profile_facts ->> 'threads_per_core')::integer,
                h.system_profile_facts ->> 'tuned_profile',
                (h.system_profile_facts ->> 'virtual_host_uuid')::uuid,
                (SELECT array_agg(value) FROM jsonb_array_elements(h.system_profile_facts -> 'yum_repos'))
            FROM {INVENTORY_SCHEMA}.hosts h
            ON CONFLICT (org_id, host_id) DO NOTHING;
        """)


def downgrade():
    # Truncate the new partitioned tables to remove the data copied during the upgrade.
    op.execute(f"TRUNCATE TABLE {INVENTORY_SCHEMA}.system_profiles_static;")
    op.execute(f"TRUNCATE TABLE {INVENTORY_SCHEMA}.system_profiles_dynamic;")

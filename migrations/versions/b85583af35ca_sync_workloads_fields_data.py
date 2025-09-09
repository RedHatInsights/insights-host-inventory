"""sync workloads fields data

Revision ID: b85583af35ca
Revises: 7580b7bc0d00
Create Date: 2025-09-04 15:12:02.234062

"""
# ruff: noqa: E501

import os

from alembic import op

from app.models.constants import INVENTORY_SCHEMA

# revision identifiers, used by Alembic.
revision = "b85583af35ca"
down_revision = "7580b7bc0d00"
branch_labels = None
depends_on = None

"""
This migration updates the 'workloads' field in the 'hosts' and
'system_profiles_dynamic' tables by synchronizing it with their related 'system_profile_facts'
fields. It ensures that the 'workloads' data is consistent across these fields.

This script's behavior is conditional based on the `MIGRATION_MODE` environment variable:

- **automated:** Performs the update of the workloads fields from the original
fields in the 'hosts.system_profile_facts' column into the tables ('hosts' and
'system_profiles_dynamic').  This mode is intended for automated setups like
local development, ephemeral and on-premise environments.

- **managed:** Skips all data operations. It only "stamps" this update as complete.
This mode is intended for stage and production environments where the data update is
performed via controlled, external script.
"""


def upgrade():
    migration_mode = os.environ.get("MIGRATION_MODE", "automated").lower()

    if migration_mode == "automated":
        # --- SQL Statements for 'hosts' table ---
        op.execute(f"""
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
        """)

        op.execute(f"""
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
        """)

        op.execute(f"""
            UPDATE {INVENTORY_SCHEMA}.hosts
            SET system_profile_facts = system_profile_facts || jsonb_build_object(
                'workloads',
                (COALESCE(system_profile_facts -> 'workloads', '{{}}'::jsonb)) || jsonb_build_object(
                    'sap', jsonb_build_object(
                        'sap_system', TRUE,
                        'sids', COALESCE(system_profile_facts -> 'sap_sids', '[]'::jsonb),
                        'instance_number', system_profile_facts -> 'sap_instance_number',
                        'version', system_profile_facts -> 'sap_version'
                    )
                )
            )
            WHERE (system_profile_facts ->> 'sap_system')::boolean IS TRUE;
        """)

        op.execute(f"""
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
        """)

        op.execute(f"""
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
        """)

        op.execute(f"""
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
        """)

        # --- SQL Statements for 'system_profiles_dynamic' table ---
        # These queries use UPDATE...FROM to join hosts and update system_profiles_dynamic based on host data.
        # --- SQL Statements for 'system_profiles_dynamic' table ---
        op.execute(f"""
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
        """)

        op.execute(f"""
            UPDATE {INVENTORY_SCHEMA}.system_profiles_dynamic spd
            SET workloads = COALESCE(spd.workloads, '{{}}'::jsonb) || jsonb_build_object(
                'mssql',
                jsonb_build_object(
                    'version', h.system_profile_facts -> 'mssql' -> 'version'
                )
            )
            FROM {INVENTORY_SCHEMA}.hosts h
            WHERE spd.host_id = h.id AND h.system_profile_facts ->> 'mssql' IS NOT NULL;
        """)

        op.execute(f"""
            UPDATE {INVENTORY_SCHEMA}.system_profiles_dynamic spd
            SET workloads = COALESCE(spd.workloads, '{{}}'::jsonb) || jsonb_build_object(
                'sap',
                jsonb_build_object(
                    'sap_system', TRUE,
                    'sids', COALESCE(h.system_profile_facts -> 'sap_sids', '[]'::jsonb),
                    'instance_number', h.system_profile_facts -> 'sap_instance_number',
                    'version', h.system_profile_facts -> 'sap_version'
                )
            )
            FROM {INVENTORY_SCHEMA}.hosts h
            WHERE spd.host_id = h.id AND (h.system_profile_facts ->> 'sap_system')::boolean IS TRUE;
        """)

        op.execute(f"""
            UPDATE {INVENTORY_SCHEMA}.system_profiles_dynamic spd
            SET workloads = COALESCE(spd.workloads, '{{}}'::jsonb) || jsonb_build_object(
                'intersystems',
                jsonb_build_object(
                    'is_intersystems', TRUE,
                    'running_instances', h.system_profile_facts -> 'intersystems' -> 'running_instances'
                )
            )
            FROM {INVENTORY_SCHEMA}.hosts h
            WHERE spd.host_id = h.id AND (h.system_profile_facts -> 'intersystems' ->> 'is_intersystems')::boolean IS TRUE;
        """)

        op.execute(f"""
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
        """)

        op.execute(f"""
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
        """)


def downgrade():
    pass

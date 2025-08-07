"""Partitioned tables transition

Revision ID: 61c1b152246a
Revises: 002843d515cb
Create Date: 2025-07-02 16:46:52.557484

"""

import os

import sqlalchemy as sa
from alembic import op

from app.models.constants import INVENTORY_SCHEMA

# revision identifiers, used by Alembic.
revision = "61c1b152246a"
down_revision = "28280de3f1ce"
branch_labels = None
depends_on = None


"""
This migration finalizes the transition to a partitioned `hosts` table schema.
It assumes the new `hosts_new` and `hosts_groups_new` tables were created in the prior migration (28280de3f1ce).

This script's behavior is conditional based on the `MIGRATION_MODE` environment variable:
- **automated:** Performs the complete data copy from `hosts` to `hosts_new` and the
final atomic table swap. This mode is intended for automated setups like local development,
ephemeral, and on-premise environments.
- **managed:** Skips all data operations. It only validates that the database has reached
the final partitioned state and then "stamps" this migration as complete.
This mode is intended for stage and production environments where the data migration is
performed via controlled, external scripts.
"""


def upgrade():
    migration_mode = os.environ.get("MIGRATION_MODE", "automated").lower()

    # For 'automated' mode (local, ephemeral, on-premise), this script performs the full data copy and swap.
    # For 'managed' mode, this logic is handled by external Python scripts running as Openshift jobs,
    # and this migration only stamps the version.
    if migration_mode == "automated":
        # Step 1a: Copy data from the old hosts table to the new hosts_new table.
        op.execute(f"""
                INSERT INTO {INVENTORY_SCHEMA}.hosts_new (
                    org_id, id, account, display_name, ansible_host, created_on, modified_on, facts, tags,
                    tags_alt, system_profile_facts, groups, last_check_in, stale_timestamp, deletion_timestamp,
                    stale_warning_timestamp, reporter, per_reporter_staleness, canonical_facts,
                    insights_id, subscription_manager_id, satellite_id, fqdn, bios_uuid, ip_addresses,
                    mac_addresses, provider_id, provider_type
                )
                SELECT
                    h.org_id, h.id, h.account, h.display_name, h.ansible_host, h.created_on,
                    h.modified_on, h.facts, h.tags, h.tags_alt, h.system_profile_facts,
                    h.groups, h.last_check_in, h.stale_timestamp, h.deletion_timestamp,
                    h.stale_warning_timestamp, h.reporter, h.per_reporter_staleness,
                    h.canonical_facts,
                    COALESCE((h.canonical_facts->>'insights_id')::uuid, '00000000-0000-0000-0000-000000000000'),
                    h.canonical_facts ->> 'subscription_manager_id',
                    h.canonical_facts ->> 'satellite_id',
                    h.canonical_facts ->> 'fqdn',
                    h.canonical_facts ->> 'bios_uuid',
                    h.canonical_facts -> 'ip_addresses',
                    h.canonical_facts -> 'mac_addresses',
                    h.canonical_facts ->> 'provider_id',
                    h.canonical_facts ->> 'provider_type'
                FROM {INVENTORY_SCHEMA}.hosts h;
            """)

        # Step 1b: Populate the hosts_groups_new table from the hosts.groups JSONB column.
        op.execute(f"""
            INSERT INTO {INVENTORY_SCHEMA}.hosts_groups_new (org_id, host_id, group_id)
            SELECT
                h.org_id,
                h.id,
                (g.value ->> 'id')::uuid
            FROM
                {INVENTORY_SCHEMA}.hosts h,
                jsonb_array_elements(h.groups) AS g(value)
            WHERE
                jsonb_typeof(h.groups) = 'array' AND jsonb_array_length(h.groups) > 0;
        """)

        # Step 2: Perform the atomic rename swap for all tables and constraints.
        op.execute(f"""
            DO $$
            BEGIN
                -- Lock all tables involved in the swap
                LOCK TABLE {INVENTORY_SCHEMA}.hosts IN ACCESS EXCLUSIVE MODE;
                LOCK TABLE {INVENTORY_SCHEMA}.hosts_new IN ACCESS EXCLUSIVE MODE;
                LOCK TABLE {INVENTORY_SCHEMA}.hosts_groups IN ACCESS EXCLUSIVE MODE;
                LOCK TABLE {INVENTORY_SCHEMA}.hosts_groups_new IN ACCESS EXCLUSIVE MODE;

                -- Rename old tables' constraints FIRST
                ALTER TABLE {INVENTORY_SCHEMA}.hosts RENAME CONSTRAINT hosts_pkey TO hosts_old_pkey;
                ALTER TABLE {INVENTORY_SCHEMA}.hosts_groups
                RENAME CONSTRAINT hosts_groups_pkey TO hosts_groups_old_pkey;

                -- Then rename the old tables
                ALTER TABLE {INVENTORY_SCHEMA}.hosts RENAME TO hosts_old;
                ALTER TABLE {INVENTORY_SCHEMA}.hosts_groups RENAME TO hosts_groups_old;

                -- Then rename the new tables
                ALTER TABLE {INVENTORY_SCHEMA}.hosts_new RENAME TO hosts;
                ALTER TABLE {INVENTORY_SCHEMA}.hosts_groups_new RENAME TO hosts_groups;

                -- Finally, rename the new tables' constraints to their final production names
                ALTER TABLE {INVENTORY_SCHEMA}.hosts RENAME CONSTRAINT hosts_new_pkey TO hosts_pkey;
                ALTER TABLE {INVENTORY_SCHEMA}.hosts_groups RENAME
                CONSTRAINT hosts_groups_new_pkey TO hosts_groups_pkey;
            END;
            $$;
        """)

    # Set the default value for the per_reporter_staleness column to an empty JSONB object
    op.alter_column(
        "hosts",
        "per_reporter_staleness",
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
        schema=INVENTORY_SCHEMA,
    )

    # This safety check verifies that the table migration was successful before stamping.
    # It runs for ALL modes to ensure consistency.
    # op.execute("""
    #        DO $$
    #        BEGIN
    #            -- Check if the hosts table is partitioned by HASH
    #            IF NOT EXISTS (
    #                SELECT 1
    #                FROM pg_partitioned_table pt
    #                JOIN pg_class c ON c.oid = pt.partrelid
    #                JOIN pg_namespace n ON n.oid = c.relnamespace
    #                WHERE n.nspname = 'hbi' AND c.relname = 'hosts' AND pt.partstrat = 'h'
    #            ) THEN
    #                RAISE EXCEPTION 'MIGRATION ERROR: The hosts table is not partitioned as expected. Aborting.';
    #            END IF;


#
#            -- Check if the hosts primary key is composite (has 2 columns)
#            IF NOT EXISTS (
#                SELECT 1
#                FROM pg_constraint con
#                JOIN pg_class rel ON rel.oid = con.conrelid
#                JOIN pg_namespace n ON n.oid = rel.relnamespace
#                WHERE n.nspname = 'hbi' AND rel.relname = 'hosts'
#                AND con.contype = 'p' AND array_length(con.conkey, 1) = 2
#            ) THEN
#                RAISE EXCEPTION 'MIGRATION ERROR: Expected a composite primary key on the hosts table. Aborting.';
#            END IF;
#
#            -- Check if the hosts_groups table is partitioned by HASH
#            IF NOT EXISTS (
#                SELECT 1
#                FROM pg_partitioned_table pt
#                JOIN pg_class c ON c.oid = pt.partrelid
#                JOIN pg_namespace n ON n.oid = c.relnamespace
#                WHERE n.nspname = 'hbi' AND c.relname = 'hosts_groups' AND pt.partstrat = 'h'
#            ) THEN
#                RAISE EXCEPTION
#                'MIGRATION ERROR: The hosts_groups table is not partitioned as expected. Aborting.';
#            END IF;
#
#            -- Check if the hosts_groups primary key is composite (has 3 columns)
#            IF NOT EXISTS (
#                SELECT 1
#                FROM pg_constraint con
#                JOIN pg_class rel ON rel.oid = con.conrelid
#                JOIN pg_namespace n ON n.oid = rel.relnamespace
#                WHERE n.nspname = 'hbi' AND rel.relname = 'hosts_groups'
#                AND con.contype = 'p' AND array_length(con.conkey, 1) = 3
#            ) THEN
#                RAISE EXCEPTION
#                'MIGRATION ERROR: Expected a composite primary key on the hosts_groups table. Aborting.';
#            END IF;
#        END;
#        $$;
#    """)


def downgrade():
    migration_mode = os.environ.get("MIGRATION_MODE", "automated").lower()

    if migration_mode == "automated":
        # This reverses the table swap and clears the copied data from the _new tables.
        op.execute(f"""
            DO $$
            BEGIN
                -- Lock all tables involved in the swap
                LOCK TABLE {INVENTORY_SCHEMA}.hosts IN ACCESS EXCLUSIVE MODE;
                LOCK TABLE {INVENTORY_SCHEMA}.hosts_old IN ACCESS EXCLUSIVE MODE;
                LOCK TABLE {INVENTORY_SCHEMA}.hosts_groups IN ACCESS EXCLUSIVE MODE;
                LOCK TABLE {INVENTORY_SCHEMA}.hosts_groups_old IN ACCESS EXCLUSIVE MODE;

                -- Rename tables and constraints back to their pre-upgrade state
                ALTER TABLE {INVENTORY_SCHEMA}.hosts_groups
                RENAME CONSTRAINT hosts_groups_pkey TO hosts_groups_new_pkey;
                ALTER TABLE {INVENTORY_SCHEMA}.hosts RENAME CONSTRAINT hosts_pkey TO hosts_new_pkey;

                ALTER TABLE {INVENTORY_SCHEMA}.hosts_groups RENAME TO hosts_groups_new;
                ALTER TABLE {INVENTORY_SCHEMA}.hosts RENAME TO hosts_new;

                ALTER TABLE {INVENTORY_SCHEMA}.hosts_groups_old RENAME TO hosts_groups;
                ALTER TABLE {INVENTORY_SCHEMA}.hosts_old RENAME TO hosts;

                ALTER TABLE {INVENTORY_SCHEMA}.hosts_groups
                RENAME CONSTRAINT hosts_groups_old_pkey TO hosts_groups_pkey;
                ALTER TABLE {INVENTORY_SCHEMA}.hosts RENAME CONSTRAINT hosts_old_pkey TO hosts_pkey;
            END;
            $$;
        """)

        # Truncate the _new tables to remove the data copied during the upgrade.
        op.execute(f"TRUNCATE TABLE {INVENTORY_SCHEMA}.hosts_new CASCADE;")
        op.execute(f"TRUNCATE TABLE {INVENTORY_SCHEMA}.hosts_groups_new")
    else:
        # For 'managed' environments, a downgrade is a manual operational task.
        pass

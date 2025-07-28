"""system_profiles_static table creation

Revision ID: 30b45455a1d2
Revises: 61c1b152246a
Create Date: 2025-07-23 15:59:07.694257

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "30b45455a1d2"
down_revision = "61c1b152246a"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "system_profiles_static",
        # --- PK COLUMNS ---
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("host_id", sa.UUID(as_uuid=True), nullable=False),
        # --- STATIC FIELDS ---
        sa.Column("arch", sa.String(length=50), nullable=True),
        sa.Column("basearch", sa.String(length=50), nullable=True),
        sa.Column("bios_release_date", sa.String(length=50), nullable=True),
        sa.Column("bios_vendor", sa.String(length=100), nullable=True),
        sa.Column("bios_version", sa.String(length=100), nullable=True),
        sa.Column("bootc_status", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("cloud_provider", sa.String(length=100), nullable=True),
        sa.Column("conversions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("cores_per_socket", sa.Integer(), nullable=True),
        sa.Column("cpu_model", sa.String(length=100), nullable=True),
        sa.Column("disk_devices", postgresql.ARRAY(postgresql.JSONB()), nullable=True),
        sa.Column("dnf_modules", postgresql.ARRAY(postgresql.JSONB()), nullable=True),
        sa.Column("enabled_services", postgresql.ARRAY(sa.String(length=512)), nullable=True),
        sa.Column("gpg_pubkeys", postgresql.ARRAY(sa.String(length=512)), nullable=True),
        sa.Column("greenboot_fallback_detected", sa.Boolean(), server_default="FALSE", nullable=True),
        sa.Column("greenboot_status", sa.String(length=5), nullable=True),
        sa.Column("host_type", sa.String(length=4), nullable=True),
        sa.Column("image_builder", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("infrastructure_type", sa.String(length=100), nullable=True),
        sa.Column("infrastructure_vendor", sa.String(length=100), nullable=True),
        sa.Column("insights_client_version", sa.String(length=50), nullable=True),
        sa.Column("installed_packages_delta", postgresql.ARRAY(sa.String(length=512)), nullable=True),
        sa.Column("installed_services", postgresql.ARRAY(sa.String(length=512)), nullable=True),
        sa.Column("intersystems", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_marketplace", sa.Boolean(), server_default="FALSE", nullable=True),
        sa.Column("katello_agent_running", sa.Boolean(), server_default="FALSE", nullable=True),
        sa.Column("number_of_cpus", sa.Integer(), nullable=True),
        sa.Column("number_of_sockets", sa.Integer(), nullable=True),
        sa.Column("operating_system", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("os_kernel_version", sa.String(length=20), nullable=True),
        sa.Column("os_release", sa.String(length=100), nullable=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("public_dns", postgresql.ARRAY(sa.String(length=100)), nullable=True),
        sa.Column("public_ipv4_addresses", postgresql.ARRAY(sa.String(length=15)), nullable=True),
        sa.Column("releasever", sa.String(length=100), nullable=True),
        sa.Column("rhc_client_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rhc_config_state", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rhel_ai", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("rhsm", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("rpm_ostree_deployments", postgresql.ARRAY(postgresql.JSONB()), nullable=True),
        sa.Column("satellite_managed", sa.Boolean(), server_default="FALSE", nullable=True),
        sa.Column("selinux_config_file", sa.String(length=128), nullable=True),
        sa.Column("selinux_current_mode", sa.String(length=10), nullable=True),
        sa.Column("subscription_auto_attach", sa.String(length=100), nullable=True),
        sa.Column("subscription_status", sa.String(length=100), nullable=True),
        sa.Column("system_purpose", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("system_update_method", sa.String(length=10), nullable=True),
        sa.Column("third_party_services", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("threads_per_core", sa.Integer(), nullable=True),
        sa.Column("tuned_profile", sa.String(length=256), nullable=True),
        sa.Column("virtual_host_uuid", sa.String(length=36), nullable=True),
        sa.Column("workloads", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("yum_repos", postgresql.ARRAY(postgresql.JSONB()), nullable=True),
        # --- CONSTRAINTS ---
        sa.PrimaryKeyConstraint("org_id", "host_id", name=op.f("pk_system_profiles_static")),
        sa.ForeignKeyConstraint(
            ["org_id", "host_id"], ["hbi.hosts.org_id", "hbi.hosts.id"], name=op.f("fk_system_profiles_static_hosts")
        ),
        sa.CheckConstraint(
            "cores_per_socket >= 0 AND cores_per_socket <= 2147483647", name="cores_per_socket_range_check"
        ),
        sa.CheckConstraint("number_of_cpus >= 0 AND number_of_cpus <= 2147483647", name="number_of_cpus_range_check"),
        sa.CheckConstraint(
            "number_of_sockets >= 0 AND number_of_sockets <= 2147483647", name="number_of_sockets_range_check"
        ),
        sa.CheckConstraint(
            "threads_per_core >= 0 AND threads_per_core <= 2147483647", name="threads_per_core_range_check"
        ),
        schema="hbi",
        postgresql_partition_by="HASH (org_id)",
    )

    # --- PARTITION CREATION ---
    op.execute(
        """
        DO $$
        BEGIN
            FOR i IN 0..31 LOOP
                EXECUTE format('CREATE TABLE hbi.system_profiles_static_p%s PARTITION
                OF hbi.system_profiles_static FOR VALUES WITH (MODULUS 32, REMAINDER %s);', i, i);
            END LOOP;
        END;
        $$;
        """
    )

    # --- INDEX CREATION ---
    op.create_index("idx_system_profiles_static_org_id", "system_profiles_static", ["org_id"], schema="hbi")
    op.create_index("idx_system_profiles_static_host_id", "system_profiles_static", ["host_id"], schema="hbi")


def downgrade():
    """
    Removes the system_profiles_static table and its partitions.
    """
    # Drop indexes first
    op.drop_index("idx_system_profiles_static_org_id", "system_profiles_static", schema="hbi")
    op.drop_index("idx_system_profiles_static_host_id", "system_profiles_static", schema="hbi")

    op.drop_table("system_profiles_static", schema="hbi")

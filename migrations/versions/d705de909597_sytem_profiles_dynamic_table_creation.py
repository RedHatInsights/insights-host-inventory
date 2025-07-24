"""sytem_profiles_dynamic table creation

Revision ID: d705de909597
Revises: 61c1b152246a
Create Date: 2025-07-21 20:46:58.570671

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "d705de909597"
down_revision = "61c1b152246a"
branch_labels = None
depends_on = None


def validate_inputs(num_partitions: int):
    """Validate input parameters"""
    if not 1 <= num_partitions <= 32:
        raise ValueError(f"Invalid number of partitions: {num_partitions}. Must be between 1 and 32.")


def upgrade():
    """
    Creates the system_profiles_dynamic table based on the design document.

    This table contains the frequently updated fields from the original system_profile
    to mitigate write amplification[cite: 45]. It is partitioned by HASH(org_id)
    to enable partition pruning for multi-tenant performance[cite: 53, 55].
    """
    op.create_table(
        "system_profiles_dynamic",
        # --- KEY COLUMNS ---
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("host_id", sa.UUID(as_uuid=True), nullable=False),
        # --- DYNAMIC FIELDS ---
        sa.Column("captured_date", sa.DateTime(timezone=True)),
        sa.Column("running_processes", sa.ARRAY(sa.String), nullable=True),
        sa.Column("last_boot_time", sa.DateTime(timezone=True)),
        sa.Column("installed_packages", sa.ARRAY(sa.String), nullable=True),
        sa.Column("network_interfaces", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("installed_products", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("cpu_flags", sa.ARRAY(sa.String), nullable=True),
        sa.Column("insights_egg_version", sa.String(50), nullable=True),
        sa.Column("kernel_modules", sa.ARRAY(sa.String), nullable=True),
        sa.Column("system_memory_bytes", sa.BigInteger, nullable=True),
        sa.Column("systemd", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # --- CONSTRAINTS ---
        sa.ForeignKeyConstraint(
            ["org_id", "host_id"], ["hbi.hosts.org_id", "hbi.hosts.id"], name=op.f("fk_system_profiles_dynamic_hosts")
        ),
        sa.PrimaryKeyConstraint("org_id", "host_id", name=op.f("pk_system_profiles_dynamic")),
        schema="hbi",
        postgresql_partition_by="HASH (org_id)",
    )

    # --- PARTITION CREATION ---
    # Create the 32 child partitions to match the vCPU count of the DB instance[cite: 54].
    op.execute(
        """
        DO $$
        BEGIN
            FOR i IN 0..31 LOOP
                EXECUTE format('CREATE TABLE hbi.system_profiles_dynamic_p%s PARTITION
                OF hbi.system_profiles_dynamic FOR VALUES WITH (MODULUS 32, REMAINDER %s);', i, i);
            END LOOP;
        END;
        $$;
        """
    )


def downgrade():
    """
    Removes the system_profiles_dynamic table and its partitions.
    """
    op.drop_table("system_profiles_dynamic", schema="hbi")

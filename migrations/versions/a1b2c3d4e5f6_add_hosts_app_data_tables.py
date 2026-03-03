"""Add hosts application data tables

Revision ID: a1b2c3d4e5f6
Revises: 619de6666f1b
Create Date: 2025-11-12 13:30:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

from app.models.constants import INVENTORY_SCHEMA
from migrations.helpers import TABLE_NUM_PARTITIONS
from migrations.helpers import validate_num_partitions

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "619de6666f1b"
branch_labels = None
depends_on = None


def create_advisor_table(num_partitions: int):
    """Create the hosts_app_data_advisor table."""
    table_name = "hosts_app_data_advisor"

    op.create_table(
        table_name,
        # --- PK COLUMNS ---
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("host_id", postgresql.UUID(as_uuid=True), nullable=False),
        # --- DATA COLUMNS ---
        sa.Column("last_updated", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recommendations", sa.Integer(), nullable=True),
        sa.Column("incidents", sa.Integer(), nullable=True),
        # --- CONSTRAINTS ---
        sa.PrimaryKeyConstraint("org_id", "host_id", name=op.f(f"pk_{table_name}")),
        sa.ForeignKeyConstraint(
            ["org_id", "host_id"],
            [f"{INVENTORY_SCHEMA}.hosts.org_id", f"{INVENTORY_SCHEMA}.hosts.id"],
            name=f"fk_{table_name}_hosts",
            ondelete="CASCADE",
        ),
        schema=INVENTORY_SCHEMA,
        postgresql_partition_by="HASH (org_id)",
    )

    # Create partitions
    for i in range(num_partitions):
        op.execute(
            text(f"""
                CREATE TABLE {INVENTORY_SCHEMA}.{table_name}_p{i}
                PARTITION OF {INVENTORY_SCHEMA}.{table_name}
                FOR VALUES WITH (MODULUS {num_partitions}, REMAINDER {i});
            """)
        )


def create_vulnerability_table(num_partitions: int):
    """Create the hosts_app_data_vulnerability table."""
    table_name = "hosts_app_data_vulnerability"

    op.create_table(
        table_name,
        # --- PK COLUMNS ---
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("host_id", postgresql.UUID(as_uuid=True), nullable=False),
        # --- DATA COLUMNS ---
        sa.Column("last_updated", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_cves", sa.Integer(), nullable=True),
        sa.Column("critical_cves", sa.Integer(), nullable=True),
        sa.Column("high_severity_cves", sa.Integer(), nullable=True),
        sa.Column("cves_with_security_rules", sa.Integer(), nullable=True),
        sa.Column("cves_with_known_exploits", sa.Integer(), nullable=True),
        # --- CONSTRAINTS ---
        sa.PrimaryKeyConstraint("org_id", "host_id", name=op.f(f"pk_{table_name}")),
        sa.ForeignKeyConstraint(
            ["org_id", "host_id"],
            [f"{INVENTORY_SCHEMA}.hosts.org_id", f"{INVENTORY_SCHEMA}.hosts.id"],
            name=f"fk_{table_name}_hosts",
            ondelete="CASCADE",
        ),
        schema=INVENTORY_SCHEMA,
        postgresql_partition_by="HASH (org_id)",
    )

    # Create partitions
    for i in range(num_partitions):
        op.execute(
            text(f"""
                CREATE TABLE {INVENTORY_SCHEMA}.{table_name}_p{i}
                PARTITION OF {INVENTORY_SCHEMA}.{table_name}
                FOR VALUES WITH (MODULUS {num_partitions}, REMAINDER {i});
            """)
        )


def create_patch_table(num_partitions: int):
    """Create the hosts_app_data_patch table."""
    table_name = "hosts_app_data_patch"

    op.create_table(
        table_name,
        # --- PK COLUMNS ---
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("host_id", postgresql.UUID(as_uuid=True), nullable=False),
        # --- DATA COLUMNS ---
        sa.Column("last_updated", sa.DateTime(timezone=True), nullable=False),
        sa.Column("installable_advisories", sa.Integer(), nullable=True),
        sa.Column("template", sa.String(255), nullable=True),
        sa.Column("rhsm_locked_version", sa.String(50), nullable=True),
        # --- CONSTRAINTS ---
        sa.PrimaryKeyConstraint("org_id", "host_id", name=op.f(f"pk_{table_name}")),
        sa.ForeignKeyConstraint(
            ["org_id", "host_id"],
            [f"{INVENTORY_SCHEMA}.hosts.org_id", f"{INVENTORY_SCHEMA}.hosts.id"],
            name=f"fk_{table_name}_hosts",
            ondelete="CASCADE",
        ),
        schema=INVENTORY_SCHEMA,
        postgresql_partition_by="HASH (org_id)",
    )

    # Create partitions
    for i in range(num_partitions):
        op.execute(
            text(f"""
                CREATE TABLE {INVENTORY_SCHEMA}.{table_name}_p{i}
                PARTITION OF {INVENTORY_SCHEMA}.{table_name}
                FOR VALUES WITH (MODULUS {num_partitions}, REMAINDER {i});
            """)
        )


def create_remediations_table(num_partitions: int):
    """Create the hosts_app_data_remediations table."""
    table_name = "hosts_app_data_remediations"

    op.create_table(
        table_name,
        # --- PK COLUMNS ---
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("host_id", postgresql.UUID(as_uuid=True), nullable=False),
        # --- DATA COLUMNS ---
        sa.Column("last_updated", sa.DateTime(timezone=True), nullable=False),
        sa.Column("remediations_plans", sa.Integer(), nullable=True),
        # --- CONSTRAINTS ---
        sa.PrimaryKeyConstraint("org_id", "host_id", name=op.f(f"pk_{table_name}")),
        sa.ForeignKeyConstraint(
            ["org_id", "host_id"],
            [f"{INVENTORY_SCHEMA}.hosts.org_id", f"{INVENTORY_SCHEMA}.hosts.id"],
            name=f"fk_{table_name}_hosts",
            ondelete="CASCADE",
        ),
        schema=INVENTORY_SCHEMA,
        postgresql_partition_by="HASH (org_id)",
    )

    # Create partitions
    for i in range(num_partitions):
        op.execute(
            text(f"""
                CREATE TABLE {INVENTORY_SCHEMA}.{table_name}_p{i}
                PARTITION OF {INVENTORY_SCHEMA}.{table_name}
                FOR VALUES WITH (MODULUS {num_partitions}, REMAINDER {i});
            """)
        )


def create_compliance_table(num_partitions: int):
    """Create the hosts_app_data_compliance table."""
    table_name = "hosts_app_data_compliance"

    op.create_table(
        table_name,
        # --- PK COLUMNS ---
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("host_id", postgresql.UUID(as_uuid=True), nullable=False),
        # --- DATA COLUMNS ---
        sa.Column("last_updated", sa.DateTime(timezone=True), nullable=False),
        sa.Column("policies", sa.Integer(), nullable=True),
        sa.Column("last_scan", sa.DateTime(timezone=True), nullable=True),
        # --- CONSTRAINTS ---
        sa.PrimaryKeyConstraint("org_id", "host_id", name=op.f(f"pk_{table_name}")),
        sa.ForeignKeyConstraint(
            ["org_id", "host_id"],
            [f"{INVENTORY_SCHEMA}.hosts.org_id", f"{INVENTORY_SCHEMA}.hosts.id"],
            name=f"fk_{table_name}_hosts",
            ondelete="CASCADE",
        ),
        schema=INVENTORY_SCHEMA,
        postgresql_partition_by="HASH (org_id)",
    )

    # Create partitions
    for i in range(num_partitions):
        op.execute(
            text(f"""
                CREATE TABLE {INVENTORY_SCHEMA}.{table_name}_p{i}
                PARTITION OF {INVENTORY_SCHEMA}.{table_name}
                FOR VALUES WITH (MODULUS {num_partitions}, REMAINDER {i});
            """)
        )


def create_malware_table(num_partitions: int):
    """Create the hosts_app_data_malware table."""
    table_name = "hosts_app_data_malware"

    op.create_table(
        table_name,
        # --- PK COLUMNS ---
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("host_id", postgresql.UUID(as_uuid=True), nullable=False),
        # --- DATA COLUMNS ---
        sa.Column("last_updated", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_status", sa.String(50), nullable=True),
        sa.Column("last_matches", sa.Integer(), nullable=True),
        sa.Column("last_scan", sa.DateTime(timezone=True), nullable=True),
        # --- CONSTRAINTS ---
        sa.PrimaryKeyConstraint("org_id", "host_id", name=op.f(f"pk_{table_name}")),
        sa.ForeignKeyConstraint(
            ["org_id", "host_id"],
            [f"{INVENTORY_SCHEMA}.hosts.org_id", f"{INVENTORY_SCHEMA}.hosts.id"],
            name=f"fk_{table_name}_hosts",
            ondelete="CASCADE",
        ),
        schema=INVENTORY_SCHEMA,
        postgresql_partition_by="HASH (org_id)",
    )

    # Create partitions
    for i in range(num_partitions):
        op.execute(
            text(f"""
                CREATE TABLE {INVENTORY_SCHEMA}.{table_name}_p{i}
                PARTITION OF {INVENTORY_SCHEMA}.{table_name}
                FOR VALUES WITH (MODULUS {num_partitions}, REMAINDER {i});
            """)
        )


def create_image_builder_table(num_partitions: int):
    """Create the hosts_app_data_image_builder table."""
    table_name = "hosts_app_data_image_builder"

    op.create_table(
        table_name,
        # --- PK COLUMNS ---
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("host_id", postgresql.UUID(as_uuid=True), nullable=False),
        # --- DATA COLUMNS ---
        sa.Column("last_updated", sa.DateTime(timezone=True), nullable=False),
        sa.Column("image_name", sa.String(255), nullable=True),
        sa.Column("image_status", sa.String(50), nullable=True),
        # --- CONSTRAINTS ---
        sa.PrimaryKeyConstraint("org_id", "host_id", name=op.f(f"pk_{table_name}")),
        sa.ForeignKeyConstraint(
            ["org_id", "host_id"],
            [f"{INVENTORY_SCHEMA}.hosts.org_id", f"{INVENTORY_SCHEMA}.hosts.id"],
            name=f"fk_{table_name}_hosts",
            ondelete="CASCADE",
        ),
        schema=INVENTORY_SCHEMA,
        postgresql_partition_by="HASH (org_id)",
    )

    # Create partitions
    for i in range(num_partitions):
        op.execute(
            text(f"""
                CREATE TABLE {INVENTORY_SCHEMA}.{table_name}_p{i}
                PARTITION OF {INVENTORY_SCHEMA}.{table_name}
                FOR VALUES WITH (MODULUS {num_partitions}, REMAINDER {i});
            """)
        )


def upgrade():
    validate_num_partitions(TABLE_NUM_PARTITIONS)

    create_advisor_table(TABLE_NUM_PARTITIONS)
    create_vulnerability_table(TABLE_NUM_PARTITIONS)
    create_patch_table(TABLE_NUM_PARTITIONS)
    create_remediations_table(TABLE_NUM_PARTITIONS)
    create_compliance_table(TABLE_NUM_PARTITIONS)
    create_malware_table(TABLE_NUM_PARTITIONS)
    create_image_builder_table(TABLE_NUM_PARTITIONS)


def downgrade():
    op.drop_table("hosts_app_data_advisor", schema=INVENTORY_SCHEMA)
    op.drop_table("hosts_app_data_vulnerability", schema=INVENTORY_SCHEMA)
    op.drop_table("hosts_app_data_patch", schema=INVENTORY_SCHEMA)
    op.drop_table("hosts_app_data_remediations", schema=INVENTORY_SCHEMA)
    op.drop_table("hosts_app_data_compliance", schema=INVENTORY_SCHEMA)
    op.drop_table("hosts_app_data_malware", schema=INVENTORY_SCHEMA)
    op.drop_table("hosts_app_data_image_builder", schema=INVENTORY_SCHEMA)

"""drop_host_app_data_image_builder

Revision ID: 5d158622cabd
Revises: 155a5b49da2e
Create Date: 2026-02-02 17:12:19.753518

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

from app.models.constants import INVENTORY_SCHEMA
from migrations.helpers import TABLE_NUM_PARTITIONS

# revision identifiers, used by Alembic.
revision = "5d158622cabd"
down_revision = "155a5b49da2e"
branch_labels = None
depends_on = None


def upgrade():
    table_name = "hosts_app_data_image_builder"

    op.drop_constraint(f"fk_{table_name}_hosts", table_name, schema=INVENTORY_SCHEMA, type_="foreignkey")
    op.drop_table(table_name, schema=INVENTORY_SCHEMA)


def downgrade():
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
    for i in range(TABLE_NUM_PARTITIONS):
        op.execute(
            text(f"""
                CREATE TABLE {INVENTORY_SCHEMA}.{table_name}_p{i}
                PARTITION OF {INVENTORY_SCHEMA}.{table_name}
                FOR VALUES WITH (MODULUS {TABLE_NUM_PARTITIONS}, REMAINDER {i});
            """)
        )

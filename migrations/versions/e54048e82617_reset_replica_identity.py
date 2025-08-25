"""Reset replica identity

Revision ID: e54048e82617
Revises: 595dbad97e20
Create Date: 2025-08-21 15:34:14.491855

"""

from alembic import op
from sqlalchemy import text

from app.models.constants import INVENTORY_SCHEMA
from migrations.helpers import TABLE_NUM_PARTITIONS

# revision identifiers, used by Alembic.
revision = "e54048e82617"
down_revision = "595dbad97e20"
branch_labels = None
depends_on = None

"""
This migration resets the replica identity on all table partitions for hosts and
system_profiles_dynamic and system_profiles_static tables.
"""


def upgrade():
    for i in range(TABLE_NUM_PARTITIONS):
        hosts_partition_name = f"{INVENTORY_SCHEMA}.hosts_p{i}"
        op.execute(text(f"ALTER TABLE {hosts_partition_name} REPLICA IDENTITY DEFAULT;"))

        sp_static_partition_name = f"{INVENTORY_SCHEMA}.system_profiles_static_p{i}"
        op.execute(text(f"ALTER TABLE {sp_static_partition_name} REPLICA IDENTITY DEFAULT;"))

        sp_dynamic_partition_name = f"{INVENTORY_SCHEMA}.system_profiles_dynamic_p{i}"
        op.execute(text(f"ALTER TABLE {sp_dynamic_partition_name} REPLICA IDENTITY DEFAULT;"))


def downgrade():
    pass

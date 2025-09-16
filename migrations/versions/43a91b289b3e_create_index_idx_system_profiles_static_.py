"""Create index idx_system_profiles_static_bootc_image_digest

Revision ID: 43a91b289b3e
Revises: 7439696a760f
Create Date: 2025-09-16 12:15:53.617317

"""

from migrations.helpers import TABLE_NUM_PARTITIONS
from utils.partitioned_table_index_helper import create_partitioned_table_index
from utils.partitioned_table_index_helper import drop_partitioned_table_index

# revision identifiers, used by Alembic.
revision = "43a91b289b3e"
down_revision = "7439696a760f"
branch_labels = None
depends_on = None


def upgrade():
    """Create index idx_system_profiles_static_bootc_image_digest on partitioned system_profiles_static table."""

    create_partitioned_table_index(
        table_name="system_profiles_static",
        index_name="idx_system_profiles_static_bootc_image_digest",
        index_definition="((bootc_status -> 'booted' ->> 'image_digest'))",
        num_partitions=TABLE_NUM_PARTITIONS,
    )


def downgrade():
    """Drop index idx_system_profiles_static_bootc_image_digest from partitioned system_profiles_static table."""

    drop_partitioned_table_index(
        table_name="system_profiles_static",
        index_name="idx_system_profiles_static_bootc_image_digest",
        num_partitions=TABLE_NUM_PARTITIONS,
    )

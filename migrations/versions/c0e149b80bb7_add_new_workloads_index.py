"""add new workloads index

Revision ID: c0e149b80bb7
Revises: 0e3773b74542
Create Date: 2025-08-27 09:52:13.383210

"""

import os

from alembic import op
from sqlalchemy import text

from app.models.constants import INVENTORY_SCHEMA

# revision identifiers, used by Alembic.
revision = "c0e149b80bb7"
down_revision = "0e3773b74542"
branch_labels = None
depends_on = None


def upgrade():
    migration_mode = os.environ.get("MIGRATION_MODE", "automated").lower()

    if migration_mode == "managed":
        with op.get_context().autocommit_block():
            op.create_index(
                "idx_hosts_system_profiles_workloads_gin",
                "hosts",
                [text("(system_profile_facts -> 'workloads')")],
                schema=INVENTORY_SCHEMA,
                postgresql_using="gin",
                postgresql_concurrently=True,
            )
    elif migration_mode == "automated":
        op.create_index(
            "idx_hosts_system_profiles_workloads_gin",
            "hosts",
            [text("(system_profile_facts -> 'workloads')")],
            schema=INVENTORY_SCHEMA,
            postgresql_using="gin",
        )


def downgrade():
    op.drop_index(
        "idx_hosts_system_profiles_workloads_gin",
        "hosts",
        [text("(system_profile_facts -> 'workloads')")],
        schema=INVENTORY_SCHEMA,
        postgresql_using="gin",
        postgresql_concurrently=True,
    )

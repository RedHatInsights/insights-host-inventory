"""Update 'All Systems' view name to sentence case and add tags column

Revision ID: 4124f5b6e6a4
Revises: 286f3c4f6e4f
Create Date: 2026-08-24 17:55:00.000000

"""

import json

from alembic import op

from app.models.constants import INVENTORY_SCHEMA

revision = "4124f5b6e6a4"
down_revision = "286f3c4f6e4f"
branch_labels = None
depends_on = None

UPDATED_CONFIG = json.dumps(
    {
        "columns": [
            {"key": "display_name"},
            {"key": "tags"},
            {"key": "group_name"},
            {"key": "operating_system"},
            {"key": "last_check_in"},
        ]
    }
)

ORIGINAL_CONFIG = json.dumps(
    {
        "columns": [
            {"key": "display_name"},
            {"key": "group_name"},
            {"key": "operating_system"},
            {"key": "last_check_in"},
        ]
    }
)


def upgrade():
    op.execute(
        f"""
        UPDATE {INVENTORY_SCHEMA}.inventory_views
        SET name = 'All systems',
            configuration = '{UPDATED_CONFIG}'::jsonb
        WHERE name = 'All Systems' AND org_id IS NULL
        """
    )


def downgrade():
    op.execute(
        f"""
        UPDATE {INVENTORY_SCHEMA}.inventory_views
        SET name = 'All Systems',
            configuration = '{ORIGINAL_CONFIG}'::jsonb
        WHERE name = 'All systems' AND org_id IS NULL
        """
    )

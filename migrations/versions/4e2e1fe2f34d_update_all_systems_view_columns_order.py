"""Update All systems view columns order

Revision ID: 4e2e1fe2f34d
Revises: a1b2c3d4e5f8
Create Date: 2026-09-09 10:32:14.486510

"""

import json

from alembic import op

from app.models.constants import INVENTORY_SCHEMA

revision = "4e2e1fe2f34d"
down_revision = "a1b2c3d4e5f8"
branch_labels = None
depends_on = None

UPDATED_CONFIG = json.dumps(
    {
        "columns": [
            {"key": "display_name"},
            {"key": "group_name"},
            {"key": "tags"},
            {"key": "operating_system"},
            {"key": "last_check_in"},
        ]
    }
)

ORIGINAL_CONFIG = json.dumps(
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


def upgrade():
    op.execute(
        f"""
        UPDATE {INVENTORY_SCHEMA}.inventory_views
        SET configuration = '{UPDATED_CONFIG}'::jsonb
        WHERE name = 'All systems' AND org_id IS NULL
        """
    )


def downgrade():
    op.execute(
        f"""
        UPDATE {INVENTORY_SCHEMA}.inventory_views
        SET name = 'All systems',
            configuration = '{ORIGINAL_CONFIG}'::jsonb
        WHERE name = 'All systems' AND org_id IS NULL
        """
    )

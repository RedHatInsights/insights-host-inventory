"""Seed 'All Systems' system view

Revision ID: 286f3c4f6e4f
Revises: b44af3749412
Create Date: 2026-08-19 11:00:00.000000

"""

import json

from alembic import op

from app.models.constants import INVENTORY_SCHEMA

# revision identifiers, used by Alembic.
revision = "286f3c4f6e4f"
down_revision = "b44af3749412"
branch_labels = None
depends_on = None

ALL_SYSTEMS_CONFIG = json.dumps(
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
        INSERT INTO {INVENTORY_SCHEMA}.inventory_views
            (org_id, name, description, configuration, org_wide, created_by)
        VALUES (
            NULL,
            'All Systems',
            'Default inventory view showing all systems.',
            '{ALL_SYSTEMS_CONFIG}'::jsonb,
            FALSE,
            NULL
        )
        """
    )


def downgrade():
    op.execute(f"DELETE FROM {INVENTORY_SCHEMA}.inventory_views WHERE name = 'All Systems' AND org_id IS NULL")

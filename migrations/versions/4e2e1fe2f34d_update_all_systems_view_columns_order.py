"""Update All systems view columns order

Revision ID: 4e2e1fe2f34d
Revises: a1b2c3d4e5f8
Create Date: 2026-09-09 10:32:14.486510

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.models.constants import INVENTORY_SCHEMA

revision = "4e2e1fe2f34d"
down_revision = "a1b2c3d4e5f8"
branch_labels = None
depends_on = None

VIEW_NAME = "All systems"

UPDATED_CONFIG = {
    "columns": [
        {"key": "display_name"},
        {"key": "group_name"},
        {"key": "tags"},
        {"key": "operating_system"},
        {"key": "last_check_in"},
    ]
}

ORIGINAL_CONFIG = {
    "columns": [
        {"key": "display_name"},
        {"key": "tags"},
        {"key": "group_name"},
        {"key": "operating_system"},
        {"key": "last_check_in"},
    ]
}

inventory_views = sa.table(
    "inventory_views",
    sa.column("name", sa.String),
    sa.column("org_id", sa.String),
    sa.column("configuration", postgresql.JSONB),
    schema=INVENTORY_SCHEMA,
)


def _set_configuration(configuration: dict) -> None:
    op.execute(
        inventory_views.update()
        .where(
            inventory_views.c.name == VIEW_NAME,
            inventory_views.c.org_id.is_(None),
        )
        .values(configuration=configuration)
    )


def upgrade():
    _set_configuration(UPDATED_CONFIG)


def downgrade():
    _set_configuration(ORIGINAL_CONFIG)

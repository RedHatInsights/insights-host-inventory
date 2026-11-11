"""Normalize legacy advisor/vulnerability view filter values

Older views saved advisor/vulnerability host filters in a pre-schema shape
(e.g. ``incident_status: "incident"`` stored as a scalar string). The current
OpenAPI response spec requires these fields to be arrays of enum values, so a
single legacy row makes the whole ``GET /views`` list fail response validation
(``Response body does not conform to specification``) and return 500.

This migration rewrites the stored ``configuration`` JSONB for every view so the
targeted fields conform: a scalar is coerced to a single-element list, only
values valid under the current enum are kept, and a field is dropped entirely
when nothing valid remains. Legacy values with no equivalent in the new schema
(e.g. ``"incident"``) are intentionally dropped.

Revision ID: c3e8a1f204bd
Revises: 77837836a5b3
Create Date: 2026-11-11 00:00:00.000000

"""

import copy

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.models.constants import INVENTORY_SCHEMA

revision = "c3e8a1f204bd"
down_revision = "77837836a5b3"
branch_labels = None
depends_on = None

# Point-in-time snapshot of the enum-constrained advisor/vulnerability host-filter
# fields and their valid values, mirroring app/models/schemas/views.py at the time
# of this migration. Kept local (not imported) so the migration stays reproducible
# even if the schema changes later.
VALID_VALUES_BY_FIELD = {
    "recommendation_severity": frozenset({"critical", "important", "moderate", "low", "not_analyzed"}),
    "incident_status": frozenset({"present", "not_present", "not_analyzed"}),
    "cve_severity": frozenset({"critical", "important", "moderate", "low", "not_evaluated"}),
    "known_exploit": frozenset({"present", "not_present", "not_evaluated"}),
    "security_rule": frozenset({"present", "not_present", "not_evaluated"}),
}

inventory_views = sa.table(
    "inventory_views",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("configuration", postgresql.JSONB),
    schema=INVENTORY_SCHEMA,
)


def _normalize_host_filters(host_filters: dict) -> bool:
    """Normalize the targeted advisor/vulnerability fields in place.

    For each field: coerce a scalar to a single-element list, keep only values
    valid under the current enum, and drop the field when nothing valid remains.
    Returns True if anything changed.
    """
    changed = False
    for field, valid_values in VALID_VALUES_BY_FIELD.items():
        if field not in host_filters:
            continue
        original = host_filters[field]
        # Coerce a scalar (e.g. legacy ``"incident"`` or a valid value stored as a
        # bare string) into a list so a salvageable value is not discarded.
        values = original if isinstance(original, list) else [original]
        # Only string values can be valid; the isinstance guard also skips unhashable
        # junk (dicts/nested lists) that would raise TypeError on set membership.
        kept = [v for v in values if isinstance(v, str) and v in valid_values]
        if kept:
            if kept != original:
                host_filters[field] = kept
                changed = True
        else:
            del host_filters[field]
            changed = True
    return changed


def _normalize_configuration(configuration) -> bool:
    """Normalize ``configuration.filters.host`` in place. Returns True if changed."""
    if not isinstance(configuration, dict):
        return False
    filters = configuration.get("filters")
    if not isinstance(filters, dict):
        return False
    host_filters = filters.get("host")
    if not isinstance(host_filters, dict):
        return False
    return _normalize_host_filters(host_filters)


def upgrade():
    conn = op.get_bind()
    rows = conn.execute(sa.select(inventory_views.c.id, inventory_views.c.configuration)).fetchall()
    for row in rows:
        configuration = copy.deepcopy(row.configuration)
        if _normalize_configuration(configuration):
            conn.execute(
                inventory_views.update().where(inventory_views.c.id == row.id).values(configuration=configuration)
            )


def downgrade():
    # Legacy values with no equivalent in the current schema are dropped on
    # upgrade and cannot be reconstructed, so this migration is not reversible.
    pass

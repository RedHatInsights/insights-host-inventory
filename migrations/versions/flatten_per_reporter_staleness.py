"""Flatten per_reporter_staleness structure

Revision ID: flatten_prs_001
Revises: 2e14a2172246
Create Date: 2025-10-30

This migration transforms per_reporter_staleness from nested dicts to flat key-value pairs.

Before: {"puptoo": {"last_check_in": "2025-01-15T10:00:00Z", "stale_timestamp": "...", ...}}
After:  {"puptoo": "2025-01-15T10:00:00Z"}
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "flatten_prs_001"
down_revision = "2e14a2172246"
branch_labels = None
depends_on = None


def upgrade():
    # Flatten per_reporter_staleness: extract only last_check_in for each reporter
    # This transformation is safe because:
    # 1. last_check_in is the only essential data (staleness timestamps are computed from it)
    # 2. Serialization layer now rebuilds the nested structure with computed values
    op.execute("""
        UPDATE hbi.hosts
        SET per_reporter_staleness = (
            SELECT jsonb_object_agg(
                key,
                value->>'last_check_in'
            )
            FROM jsonb_each(per_reporter_staleness)
        )
        WHERE per_reporter_staleness IS NOT NULL
        AND per_reporter_staleness != '{}'::jsonb
        -- Only transform if the structure is nested (has 'last_check_in' key)
        AND EXISTS (
            SELECT 1 FROM jsonb_each(per_reporter_staleness)
            WHERE value ? 'last_check_in'
        )
    """)


def downgrade():
    # Downgrade is not feasible - we can't recreate the derived timestamps
    # that were removed during upgrade (stale_timestamp, culled_timestamp, etc.)
    # Those values are now computed on-the-fly in the application layer
    raise NotImplementedError(
        "Cannot downgrade: derived staleness timestamps cannot be recreated. "
        "The flattened structure only stores last_check_in timestamps, "
        "while the nested structure included computed timestamps that are "
        "now generated dynamically by the application."
    )

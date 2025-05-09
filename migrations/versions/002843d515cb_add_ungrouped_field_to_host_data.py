"""add ungrouped field to host data

Revision ID: 002843d515cb
Revises: bfc9f9c35c66
Create Date: 2025-05-06 08:48:49.266181

"""

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "002843d515cb"
down_revision = "bfc9f9c35c66"
branch_labels = None
depends_on = None


def upgrade():
    # For each record in the Host table, update the "groups" column.
    # If the group in that JSONB column does not have the "ungrouped" field,
    # add `"ungrouped": false`.
    conn = op.get_bind()
    while True:
        result = conn.execute(
            text(
                """
                WITH batch AS (
                    SELECT id
                    FROM hbi.hosts
                    WHERE jsonb_array_length(groups) > 0 AND NOT groups->0 ? 'ungrouped'
                    LIMIT 1000
                    FOR UPDATE
                )
                UPDATE hbi.hosts
                SET groups = (
                    SELECT jsonb_agg(
                        CASE
                            WHEN NOT (group_obj ? 'ungrouped')
                            THEN group_obj || '{"ungrouped": false}'
                            ELSE group_obj
                        END
                    )
                    FROM jsonb_array_elements(hosts.groups) AS group_obj
                )
                FROM batch
                WHERE hosts.id = batch.id
                RETURNING hosts.id
                """
            )
        )
        updated = result.rowcount
        if updated == 0:
            break


def downgrade():
    pass  # No point in removing the field once it's there

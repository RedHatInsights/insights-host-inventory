"""Add tags_alt column and migrate tags data

Revision ID: 6f44b7ecd7be
Revises: ecbe7e63f6d9
Create Date: 2025-02-28 00:46:46.297631

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "6f44b7ecd7be"
down_revision = "ecbe7e63f6d9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("hosts", sa.Column("tags_alt", postgresql.JSONB(astext_type=sa.Text()), nullable=True), schema="hbi")

    op.execute("""
        UPDATE hbi.hosts h
        SET tags_alt = sub.tags_alt
        FROM (
            SELECT id, COALESCE(
                (SELECT JSONB_AGG(
                            JSONB_BUILD_OBJECT(
                                'namespace', ns.namespace,
                                'key', k.key,
                                'value', v.value
                            )
                        )
                    FROM JSONB_OBJECT_KEYS(tags) AS ns(namespace),
                        JSONB_EACH(tags -> ns.namespace) AS k(key, value),
                        JSONB_ARRAY_ELEMENTS_TEXT(k.value) AS v(value)),
                '[]'::jsonb
            ) AS tags_alt
            FROM hbi.hosts h
            WHERE (h.system_profile_facts->>'host_type' = 'edge') AND h.tags <> '{}'
        ) AS sub
        WHERE h.id = sub.id;
    """)


def downgrade():
    op.drop_column("hosts", "tags_alt", schema="hbi")

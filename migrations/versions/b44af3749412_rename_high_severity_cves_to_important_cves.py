"""Rename high_severity_cves to important_cves in hosts_app_data_vulnerability

The vulnerability engine fix (PR #2383) changed the field name from
high_severity_cves to important_cves. The old field used impact_id 6 ("High")
which doesn't exist in Red Hat's severity ranking — it was always null.
The vuln engine now sends important_cves with impact_id 5 ("Important").

Revision ID: b44af3749412
Revises: a1b2c3d4e5f7
Create Date: 2026-06-16 19:20:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "b44af3749412"
down_revision = "a1b2c3d4e5f7"
branch_labels = None
depends_on = None


def upgrade():
    """Rename high_severity_cves to important_cves."""
    op.alter_column(
        "hosts_app_data_vulnerability",
        "high_severity_cves",
        new_column_name="important_cves",
        schema="hbi",
    )


def downgrade():
    """Rename important_cves back to high_severity_cves."""
    op.alter_column(
        "hosts_app_data_vulnerability",
        "important_cves",
        new_column_name="high_severity_cves",
        schema="hbi",
    )

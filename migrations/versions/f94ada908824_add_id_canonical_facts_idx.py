"""Add id and canonical facts unique index and use for replica identity.

Revision ID: f94ada908824
Revises: 837d2ee7bbd8
Create Date: 2025-03-27 09:30:38.364871

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "f94ada908824"
down_revision = "837d2ee7bbd8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "idx_pk_canonical_facts",
        "hosts",
        ["id", "canonical_facts"],
        unique=True,
        postgresql_concurrently=True,
        if_not_exists=True,
        schema="hbi",
    )
    op.execute("ALTER TABLE hbi.hosts REPLICA IDENTITY USING INDEX idx_pk_canonical_facts")


def downgrade():
    op.drop_index(
        "idx_pk_canonical_facts",
        table_name="hosts",
        schema="hbi",
        if_exists=True,
    )
    op.execute("ALTER TABLE hbi.hosts REPLICA IDENTITY FULL")

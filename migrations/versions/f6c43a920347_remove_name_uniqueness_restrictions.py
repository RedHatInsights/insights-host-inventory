"""remove name uniqueness restrictions

Revision ID: f6c43a920347
Revises: bfc9f9c35c66
Create Date: 2025-05-01 17:30:29.838183

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "f6c43a920347"
down_revision = "bfc9f9c35c66"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index(
        "idx_groups_org_id_name_nocase",
        table_name="groups",
        postgresql_concurrently=True,
        if_exists=True,
        schema="hbi",
    )


def downgrade():
    op.create_index(
        "idx_groups_org_id_name_nocase",
        "groups",
        ["name".lower(), "org_id"],
        postgresql_concurrently=True,
        if_not_exists=True,
        schema="hbi",
    )

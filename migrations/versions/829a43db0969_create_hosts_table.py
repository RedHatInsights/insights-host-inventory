"""Create hosts table

Revision ID: 829a43db0969
Revises: 
Create Date: 2018-10-30 14:23:57.097425

"""
from alembic import op
from sqlalchemy import Column, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision = '829a43db0969'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "hosts",
        Column("id", UUID(), primary_key=True),
        Column("account", String(10)),
        Column("display_name", String(200)),
        Column("created_on", DateTime()),
        Column("modified_on", DateTime()),
        Column("facts", JSONB()),
        Column("tags", JSONB()),
        Column("canonical_facts", JSONB())
    )


def downgrade():
    op.drop_table("hosts")

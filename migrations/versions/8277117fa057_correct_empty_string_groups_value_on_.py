"""correct empty string groups value on some hosts

Revision ID: 8277117fa057
Revises: b48ad9e4c8c5
Create Date: 2023-06-06 11:26:53.810997

"""
from alembic import op
from sqlalchemy import or_
from sqlalchemy.dialects.postgresql import JSONB

from app.models import Host
from migrations.helpers import session

# revision identifiers, used by Alembic.
revision = "8277117fa057"
down_revision = "b48ad9e4c8c5"
branch_labels = None
depends_on = None


def upgrade():
    with session() as s:
        # For all hosts that have an empty string in their `groups` field,
        # set the `groups` field to an empty array instead.
        s.query(Host).filter(or_(Host.groups == JSONB.NULL, Host.groups == {})).update({Host.groups: []})
        op.alter_column("hosts", "groups", nullable=False)


def downgrade():
    # Nothing to do; we don't want to un-correct the data
    op.alter_column("hosts", "groups", nullable=True)
    pass

"""Fix hosts groups with wrong empty array value

Revision ID: dbbecd6bf7d1
Revises: 11cd38415793
Create Date: 2024-08-20 11:56:11.120018

"""

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base

from migrations.helpers import logger
from migrations.helpers import session

# revision identifiers, used by Alembic.
revision = "dbbecd6bf7d1"
down_revision = "11cd38415793"
branch_labels = None
depends_on = None


Base = declarative_base()


class Host(Base):
    __tablename__ = "hosts"
    id = Column(UUID, primary_key=True)
    groups = Column(JSONB(none_as_null=True))


def _fix_host_groups(logger_, host_query):
    filtered_query = host_query.filter(Host.groups == '"[]"')
    matched_rows = filtered_query.update({Host.groups: []})
    logger_.info("Matched rows for UPDATE: %d", matched_rows)


def upgrade():
    logger_ = logger(__name__)
    with session() as s:
        host_query = s.query(Host)
        _fix_host_groups(logger_, host_query)
    pass


def downgrade():
    # This is a data fix, the database should not have host's groups with value {}.
    # Not reverting this change
    pass

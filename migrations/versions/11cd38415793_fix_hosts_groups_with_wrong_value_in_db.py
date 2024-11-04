"""Fix hosts groups with wrong value in DB

Revision ID: 11cd38415793
Revises: ea9d9c5cb4e4
Create Date: 2024-07-19 15:12:16.100490

"""

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base

from migrations.helpers import logger
from migrations.helpers import session

"""
This code is meant to fix the hosts that contains
a wrong value for the groups field.
Today some hosts have the value of groups field equal to "{}",
which should not be possible.

It is validated that the Host MQ does not accept this value during
the host insertion anymore.

The solution is to perform an simple update call to the hosts table,
finding the hosts WHERE groups = "{}" and update it to groups = "[]"
which is current default state for new hosts that are not associated
to any inventory group.

- Stage:
    # of hosts: 0

- Prod:
    # of hosts: 45113
    Newest host created at: "2023-05-03T15:50:02.319215Z"
    Older host created at: "2023-04-11T13:50:50.960089Z"

"""

# revision identifiers, used by Alembic.
revision = "11cd38415793"
down_revision = "ea9d9c5cb4e4"
branch_labels = None
depends_on = None

Base = declarative_base()


class Host(Base):
    __tablename__ = "hosts"
    id = Column(UUID, primary_key=True)
    groups = Column(JSONB(none_as_null=True))


def _fix_host_groups(logger_, host_query):
    filtered_query = host_query.filter(Host.groups == "{}")
    matched_rows = filtered_query.update({Host.groups: "[]"})
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

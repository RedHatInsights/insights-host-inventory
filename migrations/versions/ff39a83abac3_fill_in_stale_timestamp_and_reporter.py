"""fill_in_stale_timestamp_and_reporter

Revision ID: ff39a83abac3
Revises: c6bfa7ebeaee
Create Date: 2020-02-20 14:07:13.460270

"""

from datetime import datetime
from datetime import timedelta
from datetime import timezone

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base

from migrations.helpers import session

# revision identifiers, used by Alembic.
revision = "ff39a83abac3"
down_revision = "c6bfa7ebeaee"
branch_labels = None
depends_on = None


Base = declarative_base()
NULL = None
STALE_TIMESTAMP_DELTA = timedelta(days=-14)
REPORTER = "migration"


class Host(Base):  # type: ignore [valid-type, misc]
    __tablename__ = "hosts"

    id = Column(UUID, primary_key=True)
    stale_timestamp = Column(DateTime)
    reporter = Column(String)


def _stale_timestamp():
    return datetime.now(timezone.utc) + STALE_TIMESTAMP_DELTA


def upgrade():
    stale_timestamp = _stale_timestamp()

    with session() as s:
        s.query(Host).filter(Host.stale_timestamp == NULL).update({Host.stale_timestamp: stale_timestamp})
        s.query(Host).filter(Host.reporter == NULL).update({Host.reporter: REPORTER})


def downgrade():
    with session() as s:
        s.query(Host).filter(Host.reporter == REPORTER).update({Host.stale_timestamp: NULL, Host.reporter: NULL})

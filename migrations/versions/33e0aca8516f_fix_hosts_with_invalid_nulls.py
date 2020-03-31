"""alter_mandatory_fields_to_not_null

Revision ID: 33e0aca8516f
Revises: 5544cd265053
Create Date: 2020-03-26 10:52:44.373485

"""
from alembic import op
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base

from migrations.helpers import session


# revision identifiers, used by Alembic.
revision = "33e0aca8516f"
down_revision = "5544cd265053"
branch_labels = None
depends_on = None


Base = declarative_base()
NULL = None


class Host(Base):
    __tablename__ = "hosts"

    id = Column(UUID, primary_key=True)
    account = Column(String(10))
    created_on = Column(DateTime(timezone=True))
    modified_on = Column(DateTime(timezone=True))
    canonical_facts = Column(JSONB(none_as_null=True))


COLUMNS = ("created_on", "modified_on", "account", "canonical_facts")


def _fill_in_canonical_facts(host_query):
    host_query.filter((Host.canonical_facts == NULL) | (Host.canonical_facts == JSONB.NULL)).update(
        {Host.canonical_facts: {}}
    )


def _alter_columns_null(nullable):
    for column in COLUMNS:
        op.alter_column("hosts", column, nullable=nullable)


def upgrade():
    with session() as s:
        host_query = s.query(Host)
        _fill_in_canonical_facts(host_query)

    _alter_columns_null(False)


def downgrade():
    # This is a fix, not a data change. The records should never have had NULL/'null'. Not reverting the data.

    _alter_columns_null(True)

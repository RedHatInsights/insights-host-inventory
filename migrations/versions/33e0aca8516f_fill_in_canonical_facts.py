"""alter_mandatory_fields_to_not_null

Revision ID: 33e0aca8516f
Revises: 5544cd265053
Create Date: 2020-03-26 10:52:44.373485

"""
from sqlalchemy import Column
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
    canonical_facts = Column(JSONB(none_as_null=True))


def upgrade():
    with session() as s:
        s.query(Host).filter((Host.canonical_facts == NULL) | (Host.canonical_facts == JSONB.NULL)).update(
            {Host.canonical_facts: {}}
        )


def downgrade():
    with session() as s:
        s.query(Host).filter(Host.canonical_facts == {}).update({Host.canonical_facts: NULL})

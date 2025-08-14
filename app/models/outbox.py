import uuid

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID

from app.models.constants import INVENTORY_SCHEMA
from app.models.database import db


class Outbox(db.Model):
    __tablename__ = "outbox"
    __table_args__ = ({"schema": INVENTORY_SCHEMA},)

    def __init__(
        self,
        aggregatetype,
        aggregateid,
        operation,
        version,
        payload,
        id=None,
    ):
        self.id = id or uuid.uuid4()
        self.aggregatetype = aggregatetype
        self.aggregateid = aggregateid
        self.operation = operation
        self.version = version
        self.payload = payload

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    aggregatetype = db.Column(db.String(255), nullable=False, default="hbi.hosts")
    aggregateid = db.Column(UUID(as_uuid=True), nullable=False)
    operation = db.Column(db.String(255), nullable=False)
    version = db.Column(db.String(50), nullable=False)
    payload = db.Column(JSONB, nullable=False)

    def __repr__(self):
        return f"<Outbox( \
            id={self.id}, \
            aggregatetype={self.aggregatetype}, \
            aggregateid={self.aggregateid}, \
            operation={self.operation}, \
            version={self.version}, \
            payload={self.payload})>"  # TODO check if version is needed.

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
        aggregate_type="hbi.hosts",
        aggregate_id=None,
        event_type=None,
        payload=None,
        id=None,
    ):
        self.id = id or uuid.uuid4()
        self.aggregate_type = aggregate_type
        self.aggregate_id = aggregate_id
        self.event_type = event_type
        self.payload = payload or {}

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    aggregate_type = db.Column(db.String(255), nullable=False, default="hbi.hosts")
    aggregate_id = db.Column(UUID(as_uuid=True), nullable=False)
    event_type = db.Column(db.String(255), nullable=False)
    payload = db.Column(JSONB)

    def __repr__(self):
        return f"<Outbox( \
            id={self.id}, \
            aggregate_type={self.aggregate_type}, \
            aggregate_id={self.aggregate_id}, \
            event_type={self.event_type})>"

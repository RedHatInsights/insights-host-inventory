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
        event_type,
        payload,
        id=None,
    ):
        self.id = id or uuid.uuid4()
        self.aggregatetype = aggregatetype
        self.aggregateid = aggregateid
        self.event_type = event_type
        self.payload = payload

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    aggregatetype = db.Column(db.String(255), nullable=False, default="hbi.hosts")
    aggregateid = db.Column(UUID(as_uuid=True), nullable=False)
    event_type = db.Column(db.String(255), nullable=False)
    payload = db.Column(JSONB, nullable=False)

    def __repr__(self):
        return f"<Outbox( \
            id={self.id}, \
            aggregatetype={self.aggregatetype}, \
            aggregateid={self.aggregateid}, \
            event_type={self.event_type})>"

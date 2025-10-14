import uuid

from sqlalchemy import Index
from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.culling import CONVENTIONAL_TIME_TO_DELETE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
from app.exceptions import ValidationException
from app.models.constants import INVENTORY_SCHEMA
from app.models.database import db
from app.models.utils import _time_now


class Staleness(db.Model):
    __tablename__ = "staleness"
    __table_args__ = (
        Index("idxaccstaleorgid", "org_id"),
        UniqueConstraint("org_id", name="staleness_unique_org_id"),
        {"schema": INVENTORY_SCHEMA},
    )

    def __init__(
        self,
        org_id,
        conventional_time_to_stale=None,
        conventional_time_to_stale_warning=None,
        conventional_time_to_delete=None,
    ):
        if not org_id:
            raise ValidationException("Staleness org_id cannot be null.")

        self.org_id = org_id
        self.conventional_time_to_stale = conventional_time_to_stale
        self.conventional_time_to_stale_warning = conventional_time_to_stale_warning
        self.conventional_time_to_delete = conventional_time_to_delete

    def update(self, input_acc):
        if input_acc.conventional_time_to_stale:
            self.conventional_time_to_stale = input_acc.conventional_time_to_stale
        if input_acc.conventional_time_to_stale_warning:
            self.conventional_time_to_stale_warning = input_acc.conventional_time_to_stale_warning
        if input_acc.conventional_time_to_delete:
            self.conventional_time_to_delete = input_acc.conventional_time_to_delete

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = db.Column(db.String(36), nullable=False)
    conventional_time_to_stale = db.Column(db.Integer, default=CONVENTIONAL_TIME_TO_STALE_SECONDS, nullable=False)
    conventional_time_to_stale_warning = db.Column(
        db.Integer, default=CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS, nullable=False
    )
    conventional_time_to_delete = db.Column(db.Integer, default=CONVENTIONAL_TIME_TO_DELETE_SECONDS, nullable=False)
    created_on = db.Column(db.DateTime(timezone=True), default=_time_now)
    modified_on = db.Column(db.DateTime(timezone=True), default=_time_now, onupdate=_time_now)

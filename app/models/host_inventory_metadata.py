from datetime import timedelta

from app.models.constants import INVENTORY_SCHEMA
from app.models.database import db
from app.models.utils import _time_now


class HostInventoryMetadata(db.Model):
    __tablename__ = "hbi_metadata"
    __table_args__ = ({"schema": INVENTORY_SCHEMA},)

    def __init__(self, name, type):
        self.name = name
        self.type = type

    def _update_last_succeeded(self, last_succeed_run_datetime):
        self.last_succeeded = last_succeed_run_datetime

    name = db.Column(db.String(32), primary_key=True)
    type = db.Column(db.String(32), primary_key=True)
    last_succeeded = db.Column(
        db.DateTime(timezone=True), default=_time_now() - timedelta(hours=1), onupdate=_time_now, nullable=False
    )

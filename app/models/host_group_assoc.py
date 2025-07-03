from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.models.constants import INVENTORY_SCHEMA
from app.models.database import db


class HostGroupAssoc(db.Model):
    __tablename__ = "hosts_groups"
    __table_args__ = (
        Index("idxhostsgroups", "host_id", "group_id"),
        Index("idxgroups_hosts", "group_id", "host_id"),
        UniqueConstraint("host_id", name="hosts_groups_unique_host_id"),
        {"schema": INVENTORY_SCHEMA},
    )

    def __init__(
        self,
        host_id,
        group_id,
    ):
        self.host_id = host_id
        self.group_id = group_id

    host_id = db.Column(UUID(as_uuid=True), ForeignKey(f"{INVENTORY_SCHEMA}.hosts.id"), primary_key=True)
    group_id = db.Column(UUID(as_uuid=True), ForeignKey(f"{INVENTORY_SCHEMA}.groups.id"), primary_key=True)

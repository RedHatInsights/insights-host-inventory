from sqlalchemy import ForeignKey
from sqlalchemy import ForeignKeyConstraint
from sqlalchemy import Index
from sqlalchemy.dialects.postgresql import UUID

from app.models.constants import INVENTORY_SCHEMA
from app.models.database import db


class HostGroupAssoc(db.Model):
    __tablename__ = "hosts_groups"
    __table_args__ = (
        Index("idxhostsgroups", "host_id", "group_id"),
        Index("idxgroups_hosts", "group_id", "host_id"),
        ForeignKeyConstraint(
            ["org_id", "host_id"], [f"{INVENTORY_SCHEMA}.hosts.org_id", f"{INVENTORY_SCHEMA}.hosts.id"]
        ),
        {"schema": INVENTORY_SCHEMA},
    )

    def __init__(
        self,
        host_id,
        group_id,
        org_id=None,
    ):
        self.host_id = host_id
        self.group_id = group_id
        self.org_id = org_id

    host_id = db.Column(UUID(as_uuid=True), primary_key=True)
    org_id = db.Column(db.String(36), primary_key=True)
    group_id = db.Column(UUID(as_uuid=True), ForeignKey(f"{INVENTORY_SCHEMA}.groups.id"), primary_key=True)

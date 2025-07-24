import os

from sqlalchemy import ForeignKey
from sqlalchemy import ForeignKeyConstraint
from sqlalchemy import Index
from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.common import inventory_config
from app.models.constants import INVENTORY_SCHEMA
from app.models.database import db


class HostGroupAssoc(db.Model):
    __tablename__ = "hosts_groups"
    if os.environ.get("HBI_DB_REFACT_SKIP_IN_PROD", "false").lower() != "true":
        __table_args__ = (
            Index("idxhostsgroups", "host_id", "group_id"),
            Index("idxgroups_hosts", "group_id", "host_id"),
            ForeignKeyConstraint(
                ["org_id", "host_id"], [f"{INVENTORY_SCHEMA}.hosts.org_id", f"{INVENTORY_SCHEMA}.hosts.id"]
            ),
            {"schema": INVENTORY_SCHEMA},
        )
    else:
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
        org_id=None,
    ):
        self.host_id = host_id
        self.group_id = group_id

        if not inventory_config().hbi_db_refact_skip_in_prod:
            self.org_id = org_id

    if os.environ.get("HBI_DB_REFACT_SKIP_IN_PROD", "false").lower() != "true":
        host_id = db.Column(UUID(as_uuid=True), primary_key=True)
        org_id = db.Column(db.String(36), primary_key=True)
    else:
        host_id = db.Column(UUID(as_uuid=True), ForeignKey(f"{INVENTORY_SCHEMA}.hosts.id"), primary_key=True)

    group_id = db.Column(UUID(as_uuid=True), ForeignKey(f"{INVENTORY_SCHEMA}.groups.id"), primary_key=True)

import uuid

from sqlalchemy import Index
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import UUID

from app.exceptions import InventoryException
from app.exceptions import ValidationException
from app.logging import get_logger
from app.models.constants import INVENTORY_SCHEMA
from app.models.database import db
from app.models.utils import _time_now

logger = get_logger(__name__)


class Group(db.Model):
    __tablename__ = "groups"
    __table_args__ = (
        Index("idxgrouporgid", "org_id"),
        Index("idx_groups_org_id_name_ignorecase", text("lower(name)"), "org_id", unique=False),
        Index("idxorgidungrouped", "org_id", "ungrouped"),
        {"schema": INVENTORY_SCHEMA},
    )

    def __init__(
        self,
        org_id,
        name,
        account=None,
        id=None,
        ungrouped=False,
    ):
        if not org_id:
            raise ValidationException("Group org_id cannot be null.")
        if not name:
            raise ValidationException("Group name cannot be null.")
        if id is not None:
            self.id = id

        self.org_id = org_id
        self.account = account
        self.name = name
        self.ungrouped = ungrouped

    def update_modified_on(self):
        self.modified_on = _time_now()

    def update(self, input_group):
        if input_group.name is not None:
            self.name = input_group.name
        if input_group.account is not None:
            self.account = input_group.account

    def patch(self, patch_data):
        logger.debug("patching group (id=%s) with data: %s", self.id, patch_data)
        if self.ungrouped is True:
            raise InventoryException(title="Bad Request", detail="The 'ungrouped' group can not be modified.")
        if not patch_data:
            raise InventoryException(title="Bad Request", detail="Patch json document cannot be empty.")

        if "name" in patch_data:
            self.name = patch_data["name"]
            return True

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account = db.Column(db.String(10))
    org_id = db.Column(db.String(36), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    ungrouped = db.Column(db.Boolean, default=False, nullable=False)
    created_on = db.Column(db.DateTime(timezone=True), default=_time_now, nullable=False)
    modified_on = db.Column(db.DateTime(timezone=True), default=_time_now, onupdate=_time_now, nullable=False)

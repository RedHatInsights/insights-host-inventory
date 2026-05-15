import uuid

from sqlalchemy import Computed
from sqlalchemy import Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID

from app.exceptions import InventoryException
from app.logging import get_logger
from app.models.constants import INVENTORY_SCHEMA
from app.models.database import db
from app.models.utils import _time_now

logger = get_logger(__name__)


class InventoryView(db.Model):
    __tablename__ = "inventory_views"
    __table_args__ = (
        Index("idx_inventory_views_org_id_created_by", "org_id", "created_by"),
        {"schema": INVENTORY_SCHEMA},
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = db.Column(db.String(36), nullable=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    is_system_view = db.Column(db.Boolean, Computed("org_id IS NULL"), nullable=False)
    configuration = db.Column(JSONB, nullable=False)
    org_wide = db.Column(db.Boolean, default=False, nullable=False)
    created_by = db.Column(db.String(255), nullable=True)
    created_on = db.Column(db.DateTime(timezone=True), default=_time_now, nullable=False)
    modified_on = db.Column(db.DateTime(timezone=True), default=_time_now, onupdate=_time_now, nullable=False)

    def patch(self, patch_data):
        if not patch_data:
            raise InventoryException(title="Bad Request", detail="Patch json document cannot be empty.")

        if "name" in patch_data:
            self.name = patch_data["name"]
        if "description" in patch_data:
            self.description = patch_data["description"]
        if "configuration" in patch_data:
            self.configuration = patch_data["configuration"]
        if "org_wide" in patch_data:
            self.org_wide = patch_data["org_wide"]

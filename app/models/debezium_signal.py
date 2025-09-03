import uuid

from app.models.constants import INVENTORY_SCHEMA
from app.models.database import db


# This table is used to store the signal from the debezium connector.
# The table will be registered to the debezium connector as a signal table.
# The host-inventory does need to do anything, except have this table created.
class DebeziumSignal(db.Model):
    __tablename__ = "debezium_signal"
    __table_args__ = ({"schema": INVENTORY_SCHEMA},)

    def __init__(
        self,
        type_column,
        data,
        id=None,
    ):
        super().__init__()
        self.id = id or uuid.uuid4()
        self.type_column = type_column
        self.data = data

    id = db.Column(db.String(36), primary_key=True, default=uuid.uuid4)
    type_column = db.Column(db.String(50), nullable=False, name="type", default="incremental")
    data = db.Column(db.String, nullable=True)

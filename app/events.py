import logging
from datetime import datetime
from marshmallow import fields
from marshmallow import Schema
from marshmallow import validate
from app.validators import verify_uuid_format

logger = logging.getLogger(__name__)


class HostEvent(Schema):
    id = fields.UUID()
    timestamp = fields.DateTime(format="iso8601")
    type = fields.Str()


def delete(host):
    return HostEvent(strict=True).dumps({"id": host['id'], "timestamp": datetime.utcnow(), "type": "delete"}).data
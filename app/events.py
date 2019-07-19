import logging
from datetime import datetime

from marshmallow import fields
from marshmallow import Schema

logger = logging.getLogger(__name__)


class HostEvent(Schema):
    id = fields.UUID()
    timestamp = fields.DateTime(format="iso8601")
    type = fields.Str()


def delete(id):
    return HostEvent(strict=True).dumps({"id": id, "timestamp": datetime.utcnow(), "type": "delete"}).data

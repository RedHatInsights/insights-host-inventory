import logging
from datetime import datetime
from marshmallow import Schema, fields, validate, validates, ValidationError

logger = logging.getLogger(__name__)


class HostEvent(Schema):
    id = fields.UUID()
    timestamp = fields.DateTime()
    type = fields.Str()


def delete(id):
    return HostEvent(strict=True).load(
        {"id": id, "timestamp": datetime.now(), "type": "delete"}
    )

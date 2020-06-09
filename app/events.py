import logging
from datetime import datetime

from marshmallow import fields
from marshmallow import Schema

from app.logging import threadctx
from app.serialization import serialize_canonical_facts

logger = logging.getLogger(__name__)

DELETE_EVENT_NAME = "delete"
UPDATE_EVENT_NAME = "updated"


class HostEventMetadataSchema(Schema):
    request_id = fields.Str(required=True)


class HostEvent(Schema):
    id = fields.UUID()
    metadata = fields.Nested(HostEventMetadataSchema())
    timestamp = fields.DateTime(format="iso8601")
    type = fields.Str()
    account = fields.Str()
    insights_id = fields.Str()
    request_id = fields.Str()


def delete(host):
    return (
        HostEvent()
        .dumps(
            {
                "metadata": {"request_id": threadctx.request_id},
                "timestamp": datetime.utcnow(),
                "id": host.id,
                **serialize_canonical_facts(host.canonical_facts),
                "account": host.account,
                "request_id": threadctx.request_id,
                "type": "delete",
            }
        )
        .data
    )


def message_headers(event_type):
    return {"event_type": event_type}

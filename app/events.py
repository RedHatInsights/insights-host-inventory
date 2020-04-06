import logging
from datetime import datetime

from marshmallow import fields
from marshmallow import Schema

from app.logging import threadctx
from app.serialization import serialize_canonical_facts

logger = logging.getLogger(__name__)


class HostEvent(Schema):
    id = fields.UUID()
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

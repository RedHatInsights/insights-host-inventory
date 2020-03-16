import logging
from datetime import datetime

from marshmallow import fields
from marshmallow import Schema

from app.logging import threadctx
from app.queue.egress import build_event
from app.serialization import serialize_canonical_facts
from tasks import emit_event

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


def emit_patch_event(host, metadata=None):
    key = str(host.id)
    metadata = {"request_id": threadctx.request_id}
    event = build_event("updated", host, None, metadata)
    emit_event(event, key)

import logging
from datetime import datetime

from marshmallow import fields
from marshmallow import Schema

from app.logging import threadctx
from app.models import CanonicalFacts

logger = logging.getLogger(__name__)


class HostEvent(Schema):
    id = fields.UUID()
    timestamp = fields.DateTime(format="iso8601")
    type = fields.Str()
    account = fields.Str()
    insights_id = fields.Str()
    rhel_machine_id = fields.Str()
    subscription_manager_id = fields.Str()
    satellite_id = fields.Str()
    fqdn = fields.Str()
    bios_uuid = fields.Str()
    ip_addresses = fields.List(fields.Str())
    mac_addresses = fields.List(fields.Str())
    external_id = fields.Str()
    request_id = fields.Str()


def delete(host):
    return (
        HostEvent()
        .dumps(
            {
                "timestamp": datetime.utcnow(),
                "id": host.id,
                **CanonicalFacts.to_json(host.canonical_facts),
                "account": host.account,
                "request_id": threadctx.request_id,
                "type": "delete",
            }
        )
        .data
    )

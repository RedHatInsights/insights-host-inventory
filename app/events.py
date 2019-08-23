import logging
from datetime import datetime

from marshmallow import fields
from marshmallow import Schema
from marshmallow import validate

from app.logging import threadctx
from app.models import CanonicalFacts
from app.validators import verify_uuid_format

logger = logging.getLogger(__name__)


class HostEvent(Schema):
    id = fields.UUID()
    timestamp = fields.DateTime(format="iso8601")
    type = fields.Str()
    account = fields.Str(required=True, validate=validate.Length(min=1, max=10))
    insights_id = fields.Str(validate=verify_uuid_format)
    rhel_machine_id = fields.Str(validate=verify_uuid_format)
    subscription_manager_id = fields.Str(validate=verify_uuid_format)
    satellite_id = fields.Str(validate=verify_uuid_format)
    fqdn = fields.Str(validate=validate.Length(min=1, max=255))
    bios_uuid = fields.Str(validate=verify_uuid_format)
    ip_addresses = fields.List(fields.Str(validate=validate.Length(min=1, max=255)))
    mac_addresses = fields.List(fields.Str(validate=validate.Length(min=1, max=255)))
    external_id = fields.Str(validate=validate.Length(min=1, max=500))
    request_id = fields.Str(validate=validate.Length(min=1, max=500))


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

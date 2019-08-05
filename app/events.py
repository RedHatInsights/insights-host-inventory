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
    '''
    insights_id = fields.Str(validate=verify_uuid_format)
    rhel_machine_id = fields.Str(validate=verify_uuid_format)
    subscription_manager_id = fields.Str(validate=verify_uuid_format)
    satellite_id = fields.Str(validate=verify_uuid_format)
    fqdn = fields.Str(validate=validate.Length(min=1, max=255))
    bios_uuid = fields.Str(validate=verify_uuid_format)
    ip_addresses = fields.List(fields.Str(validate=validate.Length(min=1, max=255)))
    mac_addresses = fields.List(fields.Str(validate=validate.Length(min=1, max=255)))
    external_id = fields.Str(validate=validate.Length(min=1, max=500))
    '''


def delete(id):
    return HostEvent(strict=True).dumps({"id": id, "timestamp": datetime.utcnow(), "type": "delete"}).data, ''' "insights_id": id.canonical_facts.insights_id, "rhel_machine_id": id.canonical_facts.rhel_machine_id,
                                        "subscription_manager_id": id.canonical_facts.subscription_manager_id, "satellite_id": id.canonical_facts.satellite_id, 
                                        "fqdn": id.canonical_facts.fqdn, "bios_uuid": id.canonical_facts.bios_uuid, "external_id": id.canonical_facts.external_id}).data '''
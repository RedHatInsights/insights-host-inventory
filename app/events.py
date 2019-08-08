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
    insights_id = fields.Str(validate=verify_uuid_format)
    rhel_machine_id = fields.Str(validate=verify_uuid_format)
    subscription_manager_id = fields.Str(validate=verify_uuid_format)
    satellite_id = fields.Str(validate=verify_uuid_format)
    fqdn = fields.Str(validate=validate.Length(min=1, max=255))
    bios_uuid = fields.Str(validate=verify_uuid_format)
    ip_addresses = fields.List(fields.Str(validate=validate.Length(min=1, max=255)))
    mac_addresses = fields.List(fields.Str(validate=validate.Length(min=1, max=255)))
    external_id = fields.Str(validate=validate.Length(min=1, max=500))


def delete(host):
    return HostEvent(strict=True).dumps({"id": host['id'], "insights_id": host['insights_id'], "rhel_machine_id": host['rhel_machine_id'],
                                        "subscription_manager_id": host['subscription_manager_id'], "satellite_id": host['satellite_id'],
                                        "fqdn": host['fqdn'], "bios_uuid": host['bios_uuid'], "ip_addresses": host['ip_addresses'],
                                        "mac_addresses:": host['mac_addresses'], "external_id": host['external_id'],
                                        "timestamp": datetime.utcnow(), "type": "delete"}).data
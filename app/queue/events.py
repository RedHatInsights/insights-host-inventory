import logging
from datetime import datetime
from datetime import timezone
from enum import Enum

from marshmallow import fields
from marshmallow import Schema

from app.logging import threadctx
from app.models import SystemProfileSchema
from app.models import TagsSchema
from app.serialization import serialize_canonical_facts

logger = logging.getLogger(__name__)


EventType = Enum("EventType", ("created", "updated", "delete"))


# Schemas
class HostSchema(Schema):
    id = fields.UUID()
    display_name = fields.Str()
    ansible_host = fields.Str()
    account = fields.Str(required=True)
    insights_id = fields.Str()
    rhel_machine_id = fields.Str()
    subscription_manager_id = fields.Str()
    satellite_id = fields.Str()
    fqdn = fields.Str()
    bios_uuid = fields.Str()
    ip_addresses = fields.List(fields.Str())
    mac_addresses = fields.List(fields.Str())
    external_id = fields.Str()
    # FIXME:
    # created = fields.DateTime(format="iso8601")
    # updated = fields.DateTime(format="iso8601")
    # FIXME:
    created = fields.Str()
    updated = fields.Str()
    stale_timestamp = fields.Str()
    stale_warning_timestamp = fields.Str()
    culled_timestamp = fields.Str()
    reporter = fields.Str()
    tags = fields.List(fields.Nested(TagsSchema))
    system_profile = fields.Nested(SystemProfileSchema)


class HostEventMetadataSchema(Schema):
    request_id = fields.Str(required=True)


class HostCreateUpdateEvent(Schema):
    type = fields.Str()
    host = fields.Nested(HostSchema())
    timestamp = fields.DateTime(format="iso8601")
    platform_metadata = fields.Dict()
    metadata = fields.Nested(HostEventMetadataSchema())


class HostDeleteEvent(Schema):
    id = fields.UUID()
    timestamp = fields.DateTime(format="iso8601")
    type = fields.Str()
    account = fields.Str()
    insights_id = fields.Str()
    request_id = fields.Str()
    metadata = fields.Nested(HostEventMetadataSchema())


def message_headers(event_type):
    return {"event_type": event_type.name}


def host_create_update_event(event_type, host, platform_metadata=None):
    return (
        HostCreateUpdateEvent,
        {
            "timestamp": datetime.now(timezone.utc),
            "type": event_type.name,
            "host": host,
            "platform_metadata": platform_metadata,
            "metadata": {"request_id": threadctx.request_id},
        },
    )


def host_delete_event(event_type, host):
    return (
        HostDeleteEvent,
        {
            "timestamp": datetime.now(timezone.utc),
            "type": event_type.name,
            "id": host.id,
            **serialize_canonical_facts(host.canonical_facts),
            "account": host.account,
            "request_id": threadctx.request_id,
            "metadata": {"request_id": threadctx.request_id},
        },
    )


EVENT_TYPE_MAP = {
    EventType.created: host_create_update_event,
    EventType.updated: host_create_update_event,
    EventType.delete: host_delete_event,
}


def build_event(event_type, host, **kwargs):
    build = EVENT_TYPE_MAP[event_type]
    schema, event = build(event_type, host, **kwargs)
    result = schema(strict=True).dumps(event)
    return result.data


def add_host_results_to_event_type(results):
    return EventType[results.name]

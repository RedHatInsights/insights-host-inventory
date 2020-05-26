import logging
from datetime import datetime
from datetime import timezone
from enum import Enum

from marshmallow import fields
from marshmallow import Schema

from app.models import SystemProfileSchema
from app.models import TagsSchema
from app.serialization import serialize_canonical_facts
from lib.host_repository import AddHostResults

# from app.queue import metrics

logger = logging.getLogger(__name__)

# DELETE_EVENT_NAME = "delete"
# UPDATE_EVENT_NAME = "updated"


EventTypes = Enum("EventTypes", ("created", "updated", "delete"))


# Schemas
class HostEventMetadataSchema(Schema):
    request_id = fields.Str(required=True)


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


class HostCreateUpdateEvent(Schema):
    type = fields.Str()
    host = fields.Nested(HostSchema())
    timestamp = fields.DateTime(format="iso8601")
    platform_metadata = fields.Dict()


class HostDeleteEvent(Schema):
    id = fields.UUID()
    timestamp = fields.DateTime(format="iso8601")
    type = fields.Str()
    account = fields.Str()
    insights_id = fields.Str()
    request_id = fields.Str()


def message_headers(event_type):
    return {"event_type": event_type.name}


def dumpHostCreateUpdateEvent(event_type, host, platform_metadata):
    return (
        HostCreateUpdateEvent(strict=True)
        .dumps(
            {
                "timestamp": datetime.now(timezone.utc),
                "type": event_type.name,
                "host": host,
                "platform_metadata": platform_metadata,
            }
        )
        .data
    )


def dumpHostDeleteEvent(event_type, host, request_id):
    return (
        HostDeleteEvent()
        .dumps(
            {
                "timestamp": datetime.utcnow(),
                "type": event_type.name,
                "id": host.id,
                **serialize_canonical_facts(host.canonical_facts),
                "account": host.account,
                "request_id": request_id,
            }
        )
        .data
    )


# Event Constructors
def build_event(event_type, host, *, platform_metadata=None, request_id=None):
    # using enum now. Need to handle delete events too
    if event_type == EventTypes.created or event_type == EventTypes.updated:
        return dumpHostCreateUpdateEvent(event_type, host, platform_metadata)
    if event_type == EventTypes.delete:
        return dumpHostDeleteEvent(event_type, host, request_id)
    else:
        raise ValueError(f"Invalid event type ({event_type})")


def add_host_results_to_event_type(results):
    if results == AddHostResults.created:
        return EventTypes.created
    if results == AddHostResults.updated:
        return EventTypes.updated

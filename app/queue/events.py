import logging
from datetime import datetime
from datetime import timezone

from marshmallow import fields
from marshmallow import Schema

from app.logging import threadctx
from app.models import SystemProfileSchema
from app.models import TagsSchema
from app.queue import metrics
from app.serialization import serialize_canonical_facts

logger = logging.getLogger(__name__)

DELETE_EVENT_NAME = "delete"
UPDATE_EVENT_NAME = "updated"


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


class HostDeleteEvent(Schema):
    id = fields.UUID()
    timestamp = fields.DateTime(format="iso8601")
    type = fields.Str()
    account = fields.Str()
    insights_id = fields.Str()
    request_id = fields.Str()


class HostCreateUpdateEvent(Schema):
    type = fields.Str()
    host = fields.Nested(HostSchema())
    timestamp = fields.DateTime(format="iso8601")
    platform_metadata = fields.Dict()


# Events
def delete(host):
    return (
        HostDeleteEvent()
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


def message_headers(event_type):
    return {"event_type": event_type}


# Event Constructors
def _build_event(event_type, host, *, platform_metadata=None, request_id=None):
    if event_type in ("created", "updated"):
        return (
            HostCreateUpdateEvent(strict=True)
            .dumps(
                {
                    "type": event_type,
                    "host": host,
                    "platform_metadata": platform_metadata,
                    "timestamp": datetime.now(timezone.utc),
                }
            )
            .data
        )
    else:
        raise ValueError(f"Invalid event type ({event_type})")


@metrics.egress_event_serialization_time.time()
def build_egress_topic_event(event_type, host, platform_metadata=None):
    return _build_event(event_type, host, platform_metadata=platform_metadata)


def build_event_topic_event(event_type, host, request_id=None):
    return _build_event(event_type, host, request_id=request_id)

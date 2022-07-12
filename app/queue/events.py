import logging
import os
from datetime import datetime
from datetime import timezone
from enum import Enum

from marshmallow import fields
from marshmallow import Schema

from app.logging import threadctx
from app.models import ErrorPayloadSchema
from app.models import TagsSchema
from app.queue.metrics import event_serialization_time
from app.serialization import serialize_canonical_facts

logger = logging.getLogger(__name__)


EventType = Enum("EventType", ("created", "updated", "delete", "validation_error"))


def hostname():
    return os.uname().nodename


# Schemas
class SerializedHostSchema(Schema):
    id = fields.UUID()
    display_name = fields.Str()
    ansible_host = fields.Str()
    account = fields.Str(required=True)
    org_id = fields.Str(required=False)
    insights_id = fields.Str()
    subscription_manager_id = fields.Str()
    satellite_id = fields.Str()
    fqdn = fields.Str()
    bios_uuid = fields.Str()
    ip_addresses = fields.List(fields.Str())
    mac_addresses = fields.List(fields.Str())
    provider_id = fields.Str()
    provider_type = fields.Str()
    created = fields.Str()
    updated = fields.Str()
    stale_timestamp = fields.Str()
    stale_warning_timestamp = fields.Str()
    culled_timestamp = fields.Str()
    reporter = fields.Str()
    tags = fields.List(fields.Nested(TagsSchema))
    system_profile = fields.Dict()
    per_reporter_staleness = fields.Dict()


class HostEventMetadataSchema(Schema):
    request_id = fields.Str(required=True)


class HostCreateUpdateEvent(Schema):
    type = fields.Str()
    host = fields.Nested(SerializedHostSchema())
    timestamp = fields.DateTime(format="iso8601")
    platform_metadata = fields.Dict()
    metadata = fields.Nested(HostEventMetadataSchema())


class HostDeleteEvent(Schema):
    id = fields.UUID()
    timestamp = fields.DateTime(format="iso8601")
    type = fields.Str()
    account = fields.Str()
    org_id = fields.Str()
    insights_id = fields.Str()
    request_id = fields.Str()
    metadata = fields.Nested(HostEventMetadataSchema())


class HostValidationErrorMetadataSchema(Schema):
    metadata = fields.Dict()
    payload = fields.Nested(ErrorPayloadSchema)


class HostValidationErrorEvent(Schema):
    version = fields.Str()
    bundle = fields.Str(required=True)
    application = fields.Str(required=True)
    event_type = fields.Str(required=True)
    timestamp = fields.DateTime(required=True, format="iso8601")
    account_id = fields.Str(required=True)
    org_id = fields.Str()
    context = fields.Dict()
    events = fields.List(HostValidationErrorMetadataSchema())


def message_headers(event_type: EventType, insights_id: str, rh_message_id: bytearray = None):
    header = {
        "event_type": event_type.name,
        "request_id": threadctx.request_id,
        "producer": hostname(),
        "insights_id": insights_id,
    }

    # rh_message_id ensures the message is only going to be processed once by notifications
    if rh_message_id:
        header["rh-message-id"] = rh_message_id

    return header


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
    delete_event = {
        "timestamp": datetime.now(timezone.utc),
        "type": event_type.name,
        "id": host.id,
        **serialize_canonical_facts(host.canonical_facts),
        "request_id": threadctx.request_id,
        "metadata": {"request_id": threadctx.request_id},
    }

    # a valid host must have an account or org_id or both
    if host.account:
        delete_event["account"] = host.account
    if host.org_id:
        delete_event["org_id"] = host.org_id

    return (HostDeleteEvent, delete_event)


def host_validation_error_event(event_type, host, error):
    # figure out how this works if the host isn't created
    validation_error_event = {
        "version": "v1.0.0",
        "bundle": "rhel",
        "application": "inventory",
        "event_type": event_type,  # need to change _ for -
        "timestamp": datetime.now(timezone.utc),
        "account_id": host.account,
        "org_id": host.org_id if host.org_id else None,
        "context": {},
        "events": {
            "metadata": {},
            "payload": {
                # get infos from error
                "error": {
                    "code": error.code,
                    "message": error.message,
                    "stack_trace": error.stack_trace,
                    "severity": error.severity,
                },
            },
        },
    }

    return (HostValidationErrorEvent, validation_error_event)


EVENT_TYPE_MAP = {
    EventType.created: host_create_update_event,
    EventType.updated: host_create_update_event,
    EventType.delete: host_delete_event,
    EventType.validation_error: host_validation_error_event,
}


def build_event(event_type, host, **kwargs):
    with event_serialization_time.labels(event_type.name).time():
        build = EVENT_TYPE_MAP[event_type]
        schema, event = build(event_type, host, **kwargs)
        result = schema().dumps(event)
        return result


def operation_results_to_event_type(results):
    return EventType[results.name]

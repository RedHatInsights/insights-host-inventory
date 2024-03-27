from datetime import datetime
from datetime import timezone
from enum import Enum

from marshmallow import fields
from marshmallow import Schema as MarshmallowSchema
from marshmallow import validate as marshmallow_validate

from app.logging import threadctx
from app.queue.events import hostname
from app.queue.metrics import notification_event_serialization_time

NotificationType = Enum("NotificationType", ("validation_error"))
EventSeverity = Enum("EventSeverity", ("warning", "error", "critical"))


# Schemas
class BaseMetadataSchema(MarshmallowSchema):
    metadata = fields.Dict(validate=marshmallow_validate.Equal({}))
    payload = fields.Dict()


class BaseNotificationEvent(MarshmallowSchema):
    id = fields.UUID(required=True)
    version = fields.Str(required=True, validate=marshmallow_validate.Length(max=10))
    bundle = fields.Str(required=True, validate=marshmallow_validate.Equal("rhel"))
    application = fields.Str(required=True, validate=marshmallow_validate.Equal("inventory"))
    event_type = fields.Str(required=True, validate=marshmallow_validate.OneOf(NotificationType))
    timestamp = fields.DateTime(required=True, format="iso8601")
    account_id = fields.Str(validate=marshmallow_validate.Length(min=0, max=36))
    org_id = fields.Str(required=True, validate=marshmallow_validate.Length(min=0, max=36))
    context = fields.Dict()
    events = fields.List(fields.Nested(BaseMetadataSchema()))


class HostValidationErrorContextSchema(MarshmallowSchema):
    event_name = fields.Str(required=True, validate=marshmallow_validate.Length(max=255))
    display_name = fields.Str(required=True)
    inventory_id = fields.Str()


class HostValidationErrorSchema(MarshmallowSchema):
    code = fields.Str(required=True)
    message = fields.Str(required=True, validate=marshmallow_validate.Length(max=1024))
    stack_trace = fields.Str()
    severity = fields.Str(required=True, validate=marshmallow_validate.OneOf(EventSeverity))


class HostValidationErrorPayloadSchema(MarshmallowSchema):
    request_id = fields.Str(required=True)
    host_id = fields.UUID(required=True)
    display_name = fields.Str()
    canonical_facts = fields.Dict()
    error = fields.Nested(HostValidationErrorSchema())


class HostValidationErrorMetadataSchema(BaseMetadataSchema):
    payload = fields.Nested(HostValidationErrorPayloadSchema())


class HostValidationErrorNotificationEvent(BaseNotificationEvent):
    context = fields.Nested(HostValidationErrorContextSchema())
    events = fields.List(fields.Nested(HostValidationErrorMetadataSchema()))


def host_validation_error_event(notification_type, message_id, host, detail, stack_trace=None):
    base_notification_obj = build_base_notification_obj(notification_type, message_id, host)
    event = {
        "context": {
            "event_name": "Host Validation Error",
            "display_name": host.get("display_name"),
            "inventory_id": host.get("id"),
        },
        "events": [
            {
                "metadata": {},
                "payload": {
                    "request_id": threadctx.request_id,
                    "display_name": host.get("display_name"),
                    "canonical_facts": host.get("canonical_facts"),
                    "error": {
                        "code": "VE001",
                        "message": detail,
                        "stack_trace": stack_trace,
                        "severity": EventSeverity.error,
                    },
                },
            },
        ],
    }
    return (HostValidationErrorNotificationEvent, event.update(base_notification_obj))


def notification_message_headers(event_type: NotificationType, rh_message_id: bytearray = None):
    return {
        "event_type": event_type.name,
        "request_id": threadctx.request_id,
        "producer": hostname(),
        "rh-message-id": rh_message_id,
    }


def build_notification_event(notification_type, message_id, host, detail, **kwargs):
    with notification_event_serialization_time.labels(notification_type.name).time():
        build = NOTIFICATION_TYPE_MAP[notification_type]
        schema, event = build(notification_type, message_id, host, detail, **kwargs)
        result = schema().dumps(event)
        return result


def build_base_notification_obj(notification_type, message_id, host):
    base_obj = {
        "id": message_id,
        "version": "v1.0.0",  # default value, no need to update unless we want to use newer features
        "bundle": "rhel",
        "application": "inventory",
        "event_type": notification_type.name.replace("_", "-"),
        "timestamp": datetime.now(timezone.utc),
        "account_id": host.get("account_id") or "",
        "org_id": host.get("org_id"),
    }
    return base_obj


NOTIFICATION_TYPE_MAP = {
    NotificationType.validation_error: host_validation_error_event,
}

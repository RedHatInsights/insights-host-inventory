from datetime import datetime
from datetime import timezone
from enum import Enum

from marshmallow import fields
from marshmallow import Schema as MarshmallowSchema
from marshmallow import validate as marshmallow_validate

from app.logging import threadctx
from app.queue.events import hostname
from app.queue.metrics import notification_serialization_time

NotificationType = Enum("NotificationType", ("validation_error"))
EventSeverity = Enum("EventSeverity", ("warning", "error", "critical"))


# Schemas
class EventListSchema(MarshmallowSchema):
    metadata = fields.Dict(
        validate=marshmallow_validate.Equal({})
    )  # future-proofing as per notification documentation
    payload = fields.Dict()


class NotificationSchema(MarshmallowSchema):
    id = fields.UUID(required=True)  # message_id, also sent in the reader as rh_message_id
    account_id = fields.Str(validate=marshmallow_validate.Length(min=0, max=36))  # will be removed in future PR
    org_id = fields.Str(required=True, validate=marshmallow_validate.Length(min=0, max=36))
    application = fields.Str(required=True, validate=marshmallow_validate.Equal("inventory"))
    bundle = fields.Str(required=True, validate=marshmallow_validate.Equal("rhel"))
    context = fields.Dict()
    events = fields.List(fields.Nested(EventListSchema()))
    event_type = fields.Str(required=True, validate=marshmallow_validate.OneOf(NotificationType))
    timestamp = fields.DateTime(required=True, format="iso8601")


class HostValidationErrorContextSchema(MarshmallowSchema):
    event_name = fields.Str(required=True, validate=marshmallow_validate.Length(max=255))
    display_name = fields.Str(required=True)
    inventory_id = fields.Str(required=True)


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


class HostValidationErrorEventListSchema(EventListSchema):
    payload = fields.Nested(HostValidationErrorPayloadSchema())


class HostValidationErrorNotificationSchema(NotificationSchema):
    context = fields.Nested(HostValidationErrorContextSchema())
    events = fields.List(fields.Nested(HostValidationErrorEventListSchema()))


def host_validation_error_notification(notification_type, message_id, host, detail, stack_trace=None):
    base_notification_obj = build_base_notification_obj(notification_type, message_id, host)
    notification = {
        "context": {
            "event_name": "Host Validation Error",
            "display_name": host.get("display_name"),
            "inventory_id": host.get("id"),
        },
        "events": [
            {
                "payload": {
                    "request_id": threadctx.request_id,
                    "display_name": host.get("display_name"),
                    "canonical_facts": host.get("canonical_facts"),
                    "error": {
                        "code": "VE001",
                        "message": detail,
                        "stack_trace": stack_trace,
                        "severity": EventSeverity.error.name,
                    },
                },
            },
        ],
    }
    notification.update(base_notification_obj)
    return (HostValidationErrorNotificationSchema, notification)


def notification_headers(event_type: NotificationType):
    return {
        "event_type": event_type.name,
        "request_id": threadctx.request_id,
        "producer": hostname(),
    }


def build_notification(notification_type, message_id, host, detail, **kwargs):
    with notification_serialization_time.labels(notification_type.name).time():
        build = NOTIFICATION_TYPE_MAP[notification_type]
        schema, event = build(notification_type, message_id, host, detail, **kwargs)
        result = schema().dumps(event)
        return result


def build_base_notification_obj(notification_type, message_id, host):
    base_obj = {
        "id": message_id,
        "account_id": host.get("account_id") or "",
        "org_id": host.get("org_id"),
        "application": "inventory",
        "bundle": "rhel",
        "event_type": notification_type.name.replace("_", "-"),
        "timestamp": datetime.now(timezone.utc),
    }
    return base_obj


NOTIFICATION_TYPE_MAP = {
    NotificationType.validation_error: host_validation_error_notification,
}

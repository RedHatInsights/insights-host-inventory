from datetime import datetime
from datetime import timezone
from enum import Enum

from marshmallow import fields
from marshmallow import Schema as MarshmallowSchema
from marshmallow import validate as marshmallow_validate

from app.logging import threadctx
from app.queue.events import hostname
from app.queue.metrics import event_serialization_time

NotificationType = Enum("NotificationType", ("validation_error"), "error")
event_severity = Enum("warning", "error", "critical")


# Schemas
class HostValidationErrorSchema(MarshmallowSchema):
    code = fields.Str(required=True)
    message = fields.Str(required=True, validate=marshmallow_validate.Length(max=1024))
    stack_trace = fields.Str()
    severity = fields.Str(required=True, validate=marshmallow_validate.OneOf(event_severity))


class ErrorPayloadSchema(MarshmallowSchema):
    error = fields.Nested(HostValidationErrorSchema())


class HostValidationErrorMetadataSchema(MarshmallowSchema):
    metadata = fields.Dict(validate=marshmallow_validate.Equal({}))
    payload = fields.Nested(ErrorPayloadSchema())


class HostValidationErrorNotificationEvent(MarshmallowSchema):
    id: fields.UUID(required=True)
    version = fields.Str(required=True, validate=marshmallow_validate.Length(max=10))
    bundle = fields.Str(required=True, validate=marshmallow_validate.Equal("rhel"))
    application = fields.Str(required=True, validate=marshmallow_validate.Equal("inventory"))
    event_type = fields.Str(required=True, validate=marshmallow_validate.Length(max=256))
    timestamp = fields.DateTime(required=True, format="iso8601")
    account_id = fields.Str(required=True, validate=marshmallow_validate.Length(min=0, max=36))
    org_id = fields.Str(validate=marshmallow_validate.Length(min=0, max=36))
    context = fields.Dict()
    events = fields.List(HostValidationErrorMetadataSchema())


# can be reused from events.py if I import the altered version that includes rh_message_id
def notification_message_headers(event_type: NotificationType, insights_id: str, rh_message_id: bytearray = None):
    return {  # do I need all this information?
        "event_type": event_type.name,
        "request_id": threadctx.request_id,
        "producer": hostname(),
        "insights_id": insights_id,
        "rh-message-id": rh_message_id,
    }


def host_validation_error_event(event_type, host, error):
    # figure out how this works if the host isn't created
    validation_error_event = {
        "version": "v1.0.0",
        "bundle": "rhel",
        "application": "inventory",
        "event_type": event_type.replace("_", "-"),
        "timestamp": datetime.now(timezone.utc),
        "account_id": host.account,
        "org_id": host.org_id if host.org_id else None,
        "context": {},
        "events": {
            "metadata": {},
            "payload": {
                "error": {
                    "code": error.type,
                    "message": error.title,
                    "stack_trace": error.detail,
                    "severity": error.severity,
                },
            },
        },
    }

    return (HostValidationErrorNotificationEvent, validation_error_event, error)


NOTIFICATION_TYPE_MAP = {
    NotificationType.validation_error: host_validation_error_event,
}


def build_notification_event(event_type, host, error, **kwargs):
    with event_serialization_time.labels(event_type.name).time():
        build = NOTIFICATION_TYPE_MAP[event_type]
        schema, event, error = build(event_type, host, error, **kwargs)
        result = schema().dumps(event)
        return result

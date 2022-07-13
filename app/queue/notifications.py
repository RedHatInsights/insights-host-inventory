from datetime import datetime
from datetime import timezone
from enum import Enum

from marshmallow import fields
from marshmallow import Schema

from app.logging import threadctx
from app.queue.events import hostname
from app.queue.metrics import event_serialization_time

NotificationType = Enum("NotificationType", ("validation_error"), "error")


# Schemas
class HostValidationErrorSchema(Schema):
    code = fields.Str()
    message = fields.Str()
    stack_trace = fields.Str(required=False)
    severity = fields.Str()


class ErrorPayloadSchema(Schema):
    error = fields.Nested(HostValidationErrorSchema())


class HostValidationErrorMetadataSchema(Schema):
    metadata = fields.Dict()
    payload = fields.Nested(ErrorPayloadSchema())


class HostValidationErrorNotificationEvent(Schema):
    id: fields.UUID()
    version = fields.Str()
    bundle = fields.Str(required=True)
    application = fields.Str(required=True)
    event_type = fields.Str(required=True)
    timestamp = fields.DateTime(required=True, format="iso8601")
    account_id = fields.Str(required=True)
    org_id = fields.Str()
    context = fields.Dict()
    events = fields.List(HostValidationErrorMetadataSchema())


# can be reused from events.py if I import the altered version that includes rh_message_id
def notification_message_headers(event_type: NotificationType, insights_id: str, rh_message_id: bytearray = None):
    return {
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

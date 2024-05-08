from datetime import datetime
from datetime import timezone
from enum import Enum

from marshmallow import fields
from marshmallow import Schema as MarshmallowSchema
from marshmallow import validate as marshmallow_validate

from app.logging import threadctx
from app.queue.events import hostname
from app.queue.metrics import notification_serialization_time
from app.validators import verify_satellite_id
from app.validators import verify_uuid_format

NotificationType = Enum("NotificationType", ("validation_error", "system_deleted"))
EventSeverity = Enum("EventSeverity", ("warning", "error", "critical"))


# Schemas
class EventListSchema(MarshmallowSchema):
    metadata = fields.Dict(
        validate=marshmallow_validate.Equal({})
    )  # future-proofing as per notification documentation
    payload = fields.Dict()


class NotificationSchema(MarshmallowSchema):
    account_id = fields.Str(validate=marshmallow_validate.Length(min=0, max=36))  # will be removed in future PR
    org_id = fields.Str(required=True, validate=marshmallow_validate.Length(min=0, max=36))
    application = fields.Str(required=True, validate=marshmallow_validate.Equal("inventory"))
    bundle = fields.Str(required=True, validate=marshmallow_validate.Equal("rhel"))
    context = fields.Dict()
    events = fields.List(fields.Nested(EventListSchema()))
    event_type = fields.Str(required=True, validate=marshmallow_validate.OneOf(NotificationType))
    timestamp = fields.DateTime(required=True, format="iso8601")


# Host Validation Error Notification
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


# System deleted notification
class SystemDeletedContextSchema(MarshmallowSchema):
    inventory_id = fields.Str(required=True)
    hostname = fields.Str(required=True)
    dysplay_name = fields.Str(required=True)
    rhel_version = fields.Str(required=True, validate=marshmallow_validate.Length(max=30))
    tags = fields.List(fields.Dict())


class SystemDeletedPayloadSchema(MarshmallowSchema):
    groups = fields.List(fields.Str())
    insights_id = fields.Str(required=True, validate=verify_uuid_format)
    reporter = fields.Str(required=True, validate=marshmallow_validate.Length(min=1, max=255))
    subscription_manager_id = fields.Str(required=True, validate=verify_uuid_format)
    satellite_id = fields.Str(validate=verify_satellite_id)
    system_check_in = fields.Date(fields.Dict())


class SystemDeletedEventListSchema(EventListSchema):
    payload = fields.Nested(SystemDeletedPayloadSchema())


class SystemDeletedSchema(NotificationSchema):
    context = fields.Nested(SystemDeletedContextSchema())
    events = fields.List(fields.Nested(SystemDeletedEventListSchema()))
    source = fields.Dict()


def host_validation_error_notification(notification_type, host, detail, stack_trace=None):
    base_notification_obj = build_base_notification_obj(notification_type, host)
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


def system_deleted_notification(notification_type, host):
    base_notification_obj = build_base_notification_obj(notification_type, host)

    canonical_facts = host.get("canonical_facts")
    system_profile = host.get("system_profile")
    notification = {
        "context": {
            "inventory_id": host.get("id"),
            "hostname": canonical_facts.get("fqdn", ""),
            "display_name": host.get("display_name"),
            "rhel_version": build_rhel_version(system_profile),
            "tags": host.get("tags"),
        },
        "events": [
            {
                "metadata": {},
                "payload": {
                    "insights_id": canonical_facts.get("insights_id"),
                    "subscription_manager_id": canonical_facts.get("subscription_manager_id"),
                    "satellite_id": canonical_facts.get("satellite_id"),
                    "groups": [{"id": group.id, "name": group.name} for group in host.get("groups")],
                    "reporter": host.get("reporter"),
                    "system_check_in": system_profile.get("modified_on"),
                },
            }
        ],
        "source": {
            "application": {"display_name": "Inventory"},
            "bundle": {"display_name": "Red Hat Enterprise Linux"},
            "event_type": {"display_name": "System deleted"},
        },
    }

    notification.update(base_notification_obj)
    return (SystemDeletedSchema, notification)


def build_rhel_version(system_profile: dict) -> str:
    os = system_profile.get("operating_system")
    if os:
        if os.get("name") == "rhel":
            major = os.get("major")
            minor = os.get("minor")
            return f"{major:03}.{minor:03}"
    return ""


def notification_headers(event_type: NotificationType):
    return {
        "event_type": event_type.name,
        "request_id": threadctx.request_id,
        "producer": hostname(),
    }


def build_notification(notification_type, host, **kwargs):
    with notification_serialization_time.labels(notification_type.name).time():
        build = NOTIFICATION_TYPE_MAP[notification_type]
        schema, event = build(notification_type, host, **kwargs)
        result = schema().dumps(event)
        return result


def build_base_notification_obj(notification_type, host):
    base_obj = {
        "account_id": host.get("account_id") or "",
        "org_id": host.get("org_id"),
        "application": "inventory",
        "bundle": "rhel",
        "event_type": notification_type.name.replace("_", "-"),
        "timestamp": datetime.now(timezone.utc),
    }
    return base_obj


def send_notification(notification_event_producer, notification_type, host, detail=None):
    if detail:
        notification = build_notification(notification_type, host, detail=detail)
    else:
        notification = build_notification(notification_type, host)
    headers = notification_headers(notification_type)

    notification_event_producer.write_event(notification, None, headers, wait=True)


NOTIFICATION_TYPE_MAP = {
    NotificationType.validation_error: host_validation_error_notification,
    NotificationType.system_deleted: system_deleted_notification,
}

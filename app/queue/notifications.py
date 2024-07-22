import uuid
from datetime import datetime
from datetime import timezone
from enum import Enum

from marshmallow import fields
from marshmallow import Schema as MarshmallowSchema
from marshmallow import validate as marshmallow_validate

from app.common import inventory_config
from app.logging import threadctx
from app.queue.events import hostname
from app.queue.metrics import notification_serialization_time
from app.serialization import _deserialize_tags
from app.serialization import build_rhel_version_str
from app.serialization import deserialize_canonical_facts

NotificationType = Enum(
    "NotificationType", ("validation_error", "system_deleted", "system_became_stale", "new_system_registered")
)
EventSeverity = Enum("EventSeverity", ("warning", "error", "critical"))


# Schemas
class BasePayloadSchema(MarshmallowSchema):
    groups = fields.List(fields.Dict())
    insights_id = fields.Str()
    subscription_manager_id = fields.Str(required=True)
    satellite_id = fields.Str(required=True)


class BaseContextSchema(MarshmallowSchema):
    inventory_id = fields.Str(required=True)
    # hostname is used for consistency with other notifications; corresponds to fqnd on our model
    hostname = fields.Str(required=True)
    display_name = fields.Str(required=True)
    rhel_version = fields.Str(required=True)
    tags = fields.Dict()


class BaseEventListSchema(MarshmallowSchema):
    metadata = fields.Dict(
        validate=marshmallow_validate.Equal({})
    )  # future-proofing as per notification documentation
    payload = fields.Nested(BasePayloadSchema)


class BaseNotificationSchema(MarshmallowSchema):
    org_id = fields.Str(required=True, validate=marshmallow_validate.Length(min=0, max=36))
    application = fields.Str(required=True, validate=marshmallow_validate.Equal("inventory"))
    bundle = fields.Str(required=True, validate=marshmallow_validate.Equal("rhel"))
    context = fields.Nested(BaseContextSchema)
    events = fields.List(fields.Nested(BaseEventListSchema()))
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
    stack_trace = fields.Str(required=True)
    severity = fields.Str(required=True, validate=marshmallow_validate.OneOf(EventSeverity))


class HostValidationErrorPayloadSchema(MarshmallowSchema):
    request_id = fields.Str(required=True)
    host_id = fields.UUID(required=True)
    display_name = fields.Str(required=True)
    canonical_facts = fields.Dict(required=True)
    error = fields.Nested(HostValidationErrorSchema())


class HostValidationErrorEventListSchema(BaseEventListSchema):
    payload = fields.Nested(HostValidationErrorPayloadSchema())


class HostValidationErrorNotificationSchema(BaseNotificationSchema):
    context = fields.Nested(HostValidationErrorContextSchema())
    events = fields.List(fields.Nested(HostValidationErrorEventListSchema()))


# System became stale notification
class SystemStaleContextSchema(BaseContextSchema):
    host_url = fields.Str(required=True)


class SystemStaleSchema(BaseNotificationSchema):
    context = fields.Nested(SystemStaleContextSchema())


# New system registered notification
class SystemRegisteredContextSchema(BaseContextSchema):
    host_url = fields.Str(required=True)


class SystemRegisteredPayloadSchema(BasePayloadSchema):
    reporter = fields.Str(required=True)
    system_check_in = fields.Str(required=True)


class SystemRegisteredEventListSchema(BaseEventListSchema):
    payload = fields.Nested(SystemRegisteredPayloadSchema())


class SystemRegisteredSchema(BaseNotificationSchema):
    context = fields.Nested(SystemRegisteredContextSchema())
    events = fields.List(fields.Nested(SystemRegisteredEventListSchema()))


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
                "metadata": {},
                "payload": {
                    "request_id": threadctx.request_id,
                    "display_name": host.get("display_name"),
                    "canonical_facts": deserialize_canonical_facts(host, all=True),
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
    result = HostValidationErrorNotificationSchema().dumps(notification)
    return result


def system_deleted_notification(notification_type, host):
    base_notification_obj = build_base_notification_obj(notification_type, host)

    notification_obj = populate_events(base_notification_obj, [host])

    result = BaseNotificationSchema().dumps(notification_obj)
    return result


def system_stale_notification(notification_type, host):
    base_notification_obj = build_base_notification_obj(notification_type, host)

    base_notification_obj["context"]["host_url"] = f"{inventory_config().base_url_path}/hosts/{host.get('id')}"

    notification_obj = populate_events(base_notification_obj, [host], ["reporter", "system_check_in"])

    return SystemStaleSchema().dumps(notification_obj)


def system_registered_notification(notification_type, host):
    base_notification_obj = build_base_notification_obj(notification_type, host)

    base_notification_obj["context"]["host_url"] = f"{inventory_config().base_url_path}/hosts/{host.get('id')}"

    notification_obj = populate_events(base_notification_obj, [host], ["reporter", "system_check_in"])

    return SystemRegisteredSchema().dumps(notification_obj)


def notification_headers(event_type: NotificationType):
    return {
        "event_type": event_type.name,
        "request_id": threadctx.request_id,
        "producer": hostname(),
        "rh-message-id": str(uuid.uuid4()),  # protects against duplicate processing
    }


def build_notification(notification_type, host, **kwargs):
    with notification_serialization_time.labels(notification_type.name).time():
        build = NOTIFICATION_TYPE_MAP[notification_type]
        result = build(notification_type, host, **kwargs)
        return result


def build_base_notification_obj(notification_type, host):
    base_obj = {
        "org_id": host.get("org_id"),
        "application": "inventory",
        "bundle": "rhel",
        "event_type": notification_type.name.replace("_", "-"),
        "timestamp": datetime.now(timezone.utc),
    }

    if notification_type == NotificationType.validation_error:
        return base_obj

    canonical_facts = host.get("canonical_facts", deserialize_canonical_facts(host))

    system_profile = host.get("system_profile_facts", host.get("system_profile", {}))

    complete_base_obj = {
        "context": {
            "inventory_id": host.get("id"),
            "hostname": canonical_facts.get("fqdn", ""),
            "display_name": host.get("display_name"),
            "rhel_version": build_rhel_version_str(system_profile),
            "tags": _deserialize_tags(host.get("tags")),
        },
        "events": [],
    }
    complete_base_obj.update(base_obj)
    return complete_base_obj


def populate_events(base_notification_obj, host_list, extra_fields=[]):
    for host in host_list:
        canonical_facts = host.get("canonical_facts", deserialize_canonical_facts(host))

        event_output_obj = {
            "metadata": {},
            "payload": {
                "insights_id": canonical_facts.get("insights_id", ""),
                "subscription_manager_id": canonical_facts.get("subscription_manager_id", ""),
                "satellite_id": canonical_facts.get("satellite_id", ""),
                "groups": [{"id": group.get("id"), "name": group.get("name")} for group in host.get("groups", [])],
            },
        }

        for field in extra_fields:
            event_output_obj["payload"][field] = host.get(field)

        base_notification_obj["events"].append(event_output_obj)
    return base_notification_obj


def send_notification(notification_event_producer, notification_type, host, **kwargs):
    notification = build_notification(notification_type, host, **kwargs)
    headers = notification_headers(notification_type)
    notification_event_producer.write_event(notification, None, headers, wait=True)


NOTIFICATION_TYPE_MAP = {
    NotificationType.validation_error: host_validation_error_notification,
    NotificationType.system_deleted: system_deleted_notification,
    NotificationType.system_became_stale: system_stale_notification,
    NotificationType.new_system_registered: system_registered_notification,
}

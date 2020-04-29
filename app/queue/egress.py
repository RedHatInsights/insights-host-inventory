from datetime import datetime
from datetime import timezone

from kafka import KafkaProducer
from marshmallow import fields
from marshmallow import Schema

from app.logging import get_logger
from app.logging import log_produced_message
from app.models import SystemProfileSchema
from app.models import TagsSchema
from app.queue import metrics


logger = get_logger(__name__)


class KafkaEventProducer:
    def __init__(self, config):
        logger.info("Starting KafkaEventProducer()")
        self._kafka_producer = KafkaProducer(bootstrap_servers=config.bootstrap_servers)
        self._topic = config.host_egress_topic

    def write_event(self, event, key, headers):
        try:
            k = key.encode("utf-8") if key else None
            v = event.encode("utf-8")
            h = [(hk, hv.encode("utf-8")) for hk, hv in headers.items()]
            self._kafka_producer.send(self._topic, key=k, value=v, headers=h)
            log_produced_message(logger, self._topic, event, key, headers)
            metrics.egress_message_handler_success.inc()
        except Exception:
            logger.exception("Failed to send event")
            metrics.egress_message_handler_failure.inc()

    def close(self):
        self._kafka_producer.flush()
        self._kafka_producer.close()


def _build_event(event_type, host, *, platform_metadata=None, request_id=None):
    if event_type in ("created", "updated"):
        return (
            HostEvent(strict=True)
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


class HostEvent(Schema):
    type = fields.Str()
    host = fields.Nested(HostSchema())
    timestamp = fields.DateTime(format="iso8601")
    platform_metadata = fields.Dict()

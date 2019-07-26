import json

from datetime import datetime
from kafka import KafkaProducer
from marshmallow import Schema, fields

from app.logging import get_logger
from app.queue import metrics


logger = get_logger(__name__)


def create_event_producer(config, producer_type):
    if producer_type == "kafka":
        return KafkaEventProducer(config)
    else:
        return NullEventProducer()


class KafkaEventProducer:
    def __init__(self, config):
        logger.info("Starting KafkaEventProducer()")
        self._kafka_producer = KafkaProducer(bootstrap_servers=config.bootstrap_servers)
        self._topic = config.host_egress_topic

    def write_event(self, event):
        logger.debug("Topic: %s => %s" % (self._topic, event))

        event_json = None

        with metrics.egress_event_serialization_time.time():
            event_json = json.dumps(event)

        try:
            self._kafka_producer.send(self._topic, value=event_json.encode("utf-8"))
            metrics.egress_message_handler_success.inc()
        except Exception:
            logger.exception("Failed to send event")
            metrics.egress_message_handler_failure.inc()


class NullEventProducer:
    def __init__(self):
        logger.info("Starting NullEventProducer()")

    def write_event(self, event):
        logger.debug("NullEventProducer - logging event: %s" % event)


def build_event(event_type, host, metadata):
    if event_type in ("created", "updated"):
        return build_host_event(event_type, host, metadata)
    else:
        raise ValueError(f"Invalid event type ({event_type})")


def build_host_event(event_type, host, metadata):
    # FIXME:
    if "system_profile" in host:
        del host["system_profile"]
    if "facts" in host:
        del host["facts"]

    return HostEvent(strict=True).dumps(
        {"type": event_type,
         "host": host,
         "metadata": metadata,
         "timestamp": datetime.utcnow()
        }
        ).data


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
    facts = fields.Boolean()
    system_profile = fields.Boolean()
    # FIXME:
    #created = fields.DateTime(format="iso8601")
    #updated = fields.DateTime(format="iso8601")
    # FIXME:
    created = fields.Str()
    updated = fields.Str()


class HostEvent(Schema):
    type = fields.Str()
    host = fields.Nested(HostSchema())
    timestamp = fields.DateTime(format="iso8601")
    metadata = fields.Dict()

import json

from kafka import KafkaProducer
from marshmallow import Schema, fields

from app.logging import get_logger


logger = get_logger(__name__)


def create_event_producer(config, producer_type):
    logger.info("Creating event producer type:%s" % producer_type)
    return EventProducer(config)


class EventProducer:
    def __init__(self, config):
        self._kafka_producer = KafkaProducer(bootstrap_servers=config.bootstrap_servers)
        self._topic = config.host_egress_topic

    def write_event(self, event):
        logger.debug("Topic: %s => %s" % (self._topic, event))
        self._kafka_producer.send(self._topic, value=event.encode("utf-8"))


def build_event(event_type, host, metadata):
    if event_type == "created":
        return build_host_created_event(host, metadata)
    elif event_type == "updated":
        return build_host_updated_event(host, metadata)


def build_host_created_event(host, metadata):
    return json.dumps({"type": "created",
            "host": host,
            "metadata": metadata,
            })


def build_host_updated_event(host, metadata):
    return json.dumps({"type": "updated",
            "host": host,
            "metadata": metadata,
            })


class HostSchema(Schema):
    metadata = fields.Dict()
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
    facts = fields.Boolean
    system_profile = fields.Boolean

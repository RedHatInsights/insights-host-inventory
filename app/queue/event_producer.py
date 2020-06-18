import json
from enum import Enum

from kafka import KafkaProducer

from app.logging import get_logger
from app.queue import metrics

logger = get_logger(__name__)

Topic = Enum("Topic", ("egress", "events"))


class EventProducer:
    def __init__(self, config):
        logger.info("Starting EventProducer()")
        self._kafka_producer = KafkaProducer(bootstrap_servers=config.bootstrap_servers)
        self.topics = {Topic.egress: config.host_egress_topic, Topic.events: config.event_topic}

    def write_event(self, event, key, headers, topic):
        logger.debug("Topic: %s, key: %s, event: %s, headers: %s", topic, key, event, headers)

        try:
            k = key.encode("utf-8") if key else None
            v = json.dumps(event).encode("utf-8")
            h = [(hk, hv.encode("utf-8")) for hk, hv in headers.items()]
            self._kafka_producer.send(self.topics[topic], key=k, value=v, headers=h)
            metrics.egress_message_handler_success.inc()
        except Exception:
            logger.exception("Failed to send event")
            metrics.egress_message_handler_failure.inc()

    def close(self):
        self._kafka_producer.flush()
        self._kafka_producer.close()

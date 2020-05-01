from kafka import KafkaProducer

from app.logging import get_logger
from app.queue import metrics

logger = get_logger(__name__)


class KafkaEventProducer:
    def __init__(self, config):
        logger.info("Starting KafkaEventProducer()")
        self._kafka_producer = KafkaProducer(bootstrap_servers=config.bootstrap_servers)
        self._egress_topic = config.host_egress_topic
        self._event_topic = config.event_topic

    def _write_event(self, event, key, headers, topic):
        logger.debug("Topic: %s, key: %s, event: %s, headers: %s", topic, key, event, headers)

        try:
            k = key.encode("utf-8") if key else None
            v = event.encode("utf-8")
            h = [(hk, hv.encode("utf-8")) for hk, hv in headers.items()]
            self._kafka_producer.send(topic, key=k, value=v, headers=h)
            metrics.egress_message_handler_success.inc()
        except Exception:
            logger.exception("Failed to send event")
            metrics.egress_message_handler_failure.inc()

    def write_event_events_topic(self, event, key, headers):
        self._write_event(event, key, headers, self._event_topic)

    def write_event_egress_topic(self, event, key, headers):
        self._write_event(event, key, headers, self._egress_topic)

    def flush(self):
        self._kafka_producer.flush()

    def close(self):
        self._kafka_producer.flush()
        self._kafka_producer.close()

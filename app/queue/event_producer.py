from kafka import KafkaProducer
from kafka.errors import KafkaError

from app.instrumentation import message_not_produced
from app.instrumentation import message_produced
from app.logging import get_logger

logger = get_logger(__name__)


def _encode_headers(headers):
    if "rh-message-id" in headers.keys():
        return [(hk, (hv or "").encode("utf-8")) for hk, hv in headers.items() if hk != "rh-message-id"]
    return [(hk, (hv or "").encode("utf-8")) for hk, hv in headers.items()]


class EventProducer:
    def __init__(self, config, topic):
        logger.info("Starting EventProducer()")
        self._kafka_producer = KafkaProducer(bootstrap_servers=config.bootstrap_servers, **config.kafka_producer)
        self.egress_topic = topic

    def write_event(self, event, key, headers, *, wait=False):
        logger.debug("Topic: %s, key: %s, event: %s, headers: %s", self.egress_topic, key, event, headers)

        k = key.encode("utf-8") if key else None
        v = event.encode("utf-8")
        h = _encode_headers(headers)

        try:
            send_future = self._kafka_producer.send(self.egress_topic, key=k, value=v, headers=h)
        except KafkaError as error:
            message_not_produced(logger, self.egress_topic, event, key, headers, error)
            raise error
        else:
            send_future.add_callback(message_produced, logger, event, key, headers)
            send_future.add_errback(message_not_produced, logger, self.egress_topic, event, key, headers)

            if wait:
                send_future.get()

    def close(self):
        self._kafka_producer.flush()
        self._kafka_producer.close()

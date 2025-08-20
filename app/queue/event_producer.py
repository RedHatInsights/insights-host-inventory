from confluent_kafka import KafkaError
from confluent_kafka import KafkaException
from confluent_kafka import Producer as KafkaProducer

from app.instrumentation import message_not_produced
from app.instrumentation import message_produced
from app.logging import get_logger
from app.queue.metrics import produce_large_message_failure
from app.queue.metrics import produced_message_size
from lib.outbox_repository import remove_event_from_outbox

logger = get_logger(__name__)


def _encode_headers(headers):
    return [(hk, (hv or "").encode("utf-8")) for hk, hv in headers.items()]


class MessageDetails:
    def __init__(self, topic: str, event: str, headers: list[tuple], key: str):
        self.event = event
        self.headers = headers
        self.key = key
        self.topic = topic

    def on_delivered(self, error, message):
        message_to_send = None
        if error:
            if error.code() == KafkaError.MSG_SIZE_TOO_LARGE:
                message_to_send = message
                produce_large_message_failure.inc()
            message_not_produced(logger, error, self.topic, self.event, self.key, self.headers, message_to_send)
        else:
            produced_message_size.observe(len(str(message).encode("utf-8")))
            message_produced(logger, message, self.headers)


class NullEventProducer:
    # ruff: noqa: ARG002
    """Mock EventProducer that does nothing when in replica cluster"""

    def __init__(self, config, topic):
        logger.info("Starting NullEventProducer() - Kafka operations disabled in replica cluster")
        self.mq_topic = topic

    def write_event(self, event, key, headers, *, wait=False):
        logger.debug(
            "NullEventProducer: Skipping event production in replica cluster. Topic: %s, key: %s", self.mq_topic, key
        )

    def close(self):
        logger.debug("NullEventProducer: Closing (no-op)")


class EventProducer:
    def __init__(self, config, topic):
        logger.info("Starting EventProducer()")
        self._kafka_producer = KafkaProducer({"bootstrap.servers": config.bootstrap_servers, **config.kafka_producer})
        self.mq_topic = topic

    def write_event(self, event, key, headers, *, wait=False):
        logger.debug("Topic: %s, key: %s, event: %s, headers: %s", self.mq_topic, key, event, headers)

        k = key.encode("utf-8") if key else None
        v = event.encode("utf-8")
        h = _encode_headers(headers)
        topic = self.mq_topic

        try:
            messageDetails = MessageDetails(topic, v, h, k)

            self._kafka_producer.produce(topic, v, k, callback=messageDetails.on_delivered, headers=h)
            if wait:
                self._kafka_producer.flush()
            else:
                self._kafka_producer.poll()

            # remove the event from the outbox table
            remove_event_from_outbox(key)
        except KafkaException as error:
            message_not_produced(logger, error, topic, event=v, key=k, headers=h)
            raise error
        except Exception as error:
            message_not_produced(logger, error, topic, event=v, key=k, headers=h)
            raise error

    def close(self):
        self._kafka_producer.flush()


def create_event_producer(config, topic):
    """Factory function to create appropriate EventProducer"""
    if config.replica_namespace:
        return NullEventProducer(config, topic)
    return EventProducer(config, topic)

from confluent_kafka import Producer as KafkaProducer
from confluent_kafka.error import KafkaError

from app.instrumentation import message_not_produced
from app.instrumentation import message_produced
from app.logging import get_logger

logger = get_logger(__name__)


def delivery_callback(err, msg):
    if err:
        logger.error("Message not produced.")
        message_not_produced(logger, err)

    else:
        logger.info("Message produced!")
        message_produced(logger, msg)


class EventProducer:
    def __init__(self, config):
        logger.info("Starting EventProducer()")
        self._kafka_producer = KafkaProducer({"bootstrap.servers": config.bootstrap_servers})
        self.egress_topic = config.event_topic

    # TODO: Remove wait parameter
    def write_event(self, event, key, headers, *, wait=False):
        logger.debug("Topic: %s, key: %s, event: %s, headers: %s", self.egress_topic, key, event, headers)

        try:
            self._kafka_producer.produce(self.egress_topic, event, callback=delivery_callback)
            self._kafka_producer.poll()
        except KafkaError as error:
            message_not_produced(logger, error)
            raise error

    def close(self):
        self._kafka_producer.flush()
        self._kafka_producer.close()

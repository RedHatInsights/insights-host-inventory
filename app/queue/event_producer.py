# from confluent_kafka import KafkaError
from confluent_kafka import KafkaException
from confluent_kafka import Producer as KafkaProducer

from app.instrumentation import message_not_produced
from app.instrumentation import message_produced
from app.logging import get_logger

# from confluent_kafka.error import KafkaError

logger = get_logger(__name__)

__event__ = None
__headers__ = None
__key__ = None
__topic__ = None


def delivery_callback(error, message):
    if error:
        logger.error("Message not produced.")
        message_not_produced(logger, error, __event__, __topic__, __key__, __headers__)

    else:
        logger.info("Message produced!")
        message_produced(logger, message, __key__, __headers__)


class EventProducer:
    def __init__(self, config):
        logger.info("Starting EventProducer()")
        self._kafka_producer = KafkaProducer({"bootstrap.servers": config.bootstrap_servers})
        self.egress_topic = config.event_topic

    # TODO: Remove wait parameter
    def write_event(self, event, key, headers):
        logger.debug("Topic: %s, key: %s, event: %s, headers: %s", self.egress_topic, key, event, headers)

        global __event__
        global __headers__
        global __key__
        global __topic__

        __key__ = key.encode("utf-8") if key else None
        __event__ = event.encode("utf-8")
        __headers__ = [(hk, (hv or "").encode("utf-8")) for hk, hv in headers.items()]
        __topic__ = self.egress_topic

        try:
            # TODO: if __value__ does not work, use "event" as passed in
            self._kafka_producer.produce(__topic__, __event__, callback=delivery_callback)
            self._kafka_producer.poll()
        # except KafkaError as error:
        except KafkaException as error:
            message_not_produced(logger, error, __event__, __topic__, __key__, __headers__)
            raise error

    def close(self):
        self._kafka_producer.flush()
        self._kafka_producer.close()

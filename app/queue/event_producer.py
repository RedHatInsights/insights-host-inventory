from kafka import KafkaProducer
from kafka.errors import KafkaError

from app.instrumentation import message_not_produced
from app.instrumentation import message_produced
from app.logging import get_logger

logger = get_logger(__name__)


class EventProducer:
    def __init__(self, config):
        logger.info("Starting EventProducer()")
        self._kafka_producer = KafkaProducer(bootstrap_servers=config.bootstrap_servers, **config.kafka_producer)
        self.egress_topic = config.event_topic

    def write_event(self, event, key, headers, *, wait=False):
        logger.debug("Topic: %s, key: %s, event: %s, headers: %s", self.egress_topic, key, event, headers)

        k = key.encode("utf-8") if key else None
        v = event.encode("utf-8")
        h = [(hk, (hv or "").encode("utf-8")) for hk, hv in headers.items()]

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


class NotificationEventProducer:
    def __init__(self, config):
        logger.info("Starting NotificationEventProducer()")
        self._kafka_producer = KafkaProducer(bootstrap_servers=config.bootstrap_servers, **config.kafka_producer)
        self.egress_topic = config.notification_topic

    # check what else needs to be changed
    def write_event(self, event, key, headers, *, wait=False):
        logger.debug("Topic: %s, key: %s, event: %s, headers: %s", self.egress_topic, key, event, headers)

        k = key.encode("utf-8") if key else None
        v = event.encode("utf-8")
        h = [(hk, (hv or "").encode("utf-8")) for hk, hv in headers.items() if hk != "rh-message-id"]

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

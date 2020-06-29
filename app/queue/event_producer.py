from enum import Enum

from kafka import KafkaProducer
from kafka.errors import KafkaError

from app.instrumentation import message_not_produced
from app.instrumentation import message_produced
from app.logging import get_logger

logger = get_logger(__name__)

Topic = Enum("Topic", ("egress", "events"))


class EventProducer:
    def __init__(self, config):
        logger.info("Starting EventProducer()")
        self._kafka_producer = KafkaProducer(bootstrap_servers=config.bootstrap_servers)
        self.topics = {Topic.egress: config.host_egress_topic, Topic.events: config.event_topic}

    def write_event(self, event, key, headers, topic):
        logger.debug("Topic: %s, key: %s, event: %s, headers: %s", topic, key, event, headers)

        k = key.encode("utf-8") if key else None
        v = event.encode("utf-8")
        h = [(hk, hv.encode("utf-8")) for hk, hv in headers.items()]

        try:
            send_future = self._kafka_producer.send(self.topics[topic], key=k, value=v, headers=h)
        except KafkaError as error:
            message_not_produced(logger, self.topics[topic], event, key, headers, error)
        else:
            send_future.add_callback(message_produced, logger, event, key, headers)
            send_future.add_errback(message_not_produced, logger, self.topics[topic], event, key, headers)

    def close(self):
        self._kafka_producer.flush()
        self._kafka_producer.close()

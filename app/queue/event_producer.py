from confluent_kafka import KafkaException
from confluent_kafka import Producer as KafkaProducer

from app.instrumentation import message_not_produced
from app.instrumentation import message_produced
from app.logging import get_logger


logger = get_logger(__name__)


class MessageDetails:
    event: str
    headers: list(tuple())
    key: str
    topic: str

    def __init__(self, topic, event, headers, key):
        self.event = event
        self.headers = headers
        self.key = key
        self.topic = topic

    def send(self, producer):
        producer.produce(self.topic, self.event, callback=self.on_delivered)
        producer.poll()

    def on_delivered(self, error, message):
        if error:
            message_not_produced(logger, error, self.topic, self.event, self.key, self.headers)

        else:
            message_produced(logger, message, self.key, self.headers)


class EventProducer:
    def __init__(self, config):
        logger.info("Starting EventProducer()")
        self._kafka_producer = KafkaProducer({"bootstrap.servers": config.bootstrap_servers, **config.kafka_producer})
        self.egress_topic = config.event_topic
        self._message_details = MessageDetails(topic=None, event=None, headers=None, key=None)

    def write_event(self, event, key, headers):
        logger.debug("Topic: %s, key: %s, event: %s, headers: %s", self.egress_topic, key, event, headers)

        k = key.encode("utf-8") if key else None
        v = event.encode("utf-8")
        h = [(hk, (hv or "").encode("utf-8")) for hk, hv in headers.items()]
        topic = self.egress_topic

        try:
            self._message_details.topic = self.egress_topic
            self._message_details.event = v
            self._message_details.headers = h
            self._message_details.key = k
            self._message_details.send(self._kafka_producer)
        except KafkaException as error:
            message_not_produced(logger, error, topic, event=v, key=k, headers=h)
            raise error
        except Exception as error:
            message_not_produced(logger, error, topic, event=v, key=k, headers=h)
            raise error

    def close(self):
        self._kafka_producer.flush()
        self._kafka_producer.close()

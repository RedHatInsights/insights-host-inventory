from datetime import datetime

from confluent_kafka import KafkaException
from confluent_kafka import Producer as KafkaProducer

from app.instrumentation import message_not_produced
from app.instrumentation import message_produced
from app.logging import get_logger

logger = get_logger(__name__)


def _encode_headers(headers):
    if "rh-message-id" in headers.keys():
        return [(hk, (hv or "").encode("utf-8")) for hk, hv in headers.items() if hk != "rh-message-id"]
    return [(hk, (hv or "").encode("utf-8")) for hk, hv in headers.items()]


class MessageDetails:
    def __init__(self, topic: str, event: str, headers: list(tuple()), key: str):
        self.event = event
        self.headers = headers
        self.key = key
        self.topic = topic

    def on_delivered(self, error, message):
        enterTime = datetime.now()
        logger.info(f"TIMECHECK: app.queue.event_producer.MessageDetails.on_delivered() enter time: {enterTime}")

        if error:
            message_not_produced(logger, error, self.topic, self.event, self.key, self.headers)
        else:
            message_produced(logger, message, self.headers)

        execTime = (datetime.now()-enterTime).microseconds
        logger.info(f"TIMECHECK: app.queue.event_producer.MessageDetails.on_delivered() execution time: {execTime} microseconds")


class EventProducer:
    def __init__(self, config, topic):
        logger.info("Starting EventProducer()")
        self._kafka_producer = KafkaProducer({"bootstrap.servers": config.bootstrap_servers, **config.kafka_producer})
        self.egress_topic = topic

    def write_event(self, event, key, headers, *, wait=False):
        enterTime = datetime.now()
        logger.info(f"TIMECHECK: app.queue.event_producer.EventProducer.write_event() enter time: {enterTime}")

        logger.debug("Topic: %s, key: %s, event: %s, headers: %s", self.egress_topic, key, event, headers)

        k = key.encode("utf-8") if key else None
        v = event.encode("utf-8")
        h = _encode_headers(headers)
        topic = self.egress_topic

        try:
            messageDetails = MessageDetails(topic, v, h, k)

            self._kafka_producer.produce(topic, v, k, callback=messageDetails.on_delivered, headers=h)
            if wait:
                self._kafka_producer.flush()
            else:
                self._kafka_producer.poll()
        except KafkaException as error:
            message_not_produced(logger, error, topic, event=v, key=k, headers=h)
            raise error
        except Exception as error:
            message_not_produced(logger, error, topic, event=v, key=k, headers=h)
            raise error

        execTime = (datetime.now()-enterTime).microseconds
        logger.info(f"TIMECHECK: app.queue.event_producer.EventProducer.write_event() execution time: {execTime} microseconds")

    def close(self):
        self._kafka_producer.flush()
        self._kafka_producer.close()

# import sys
from confluent_kafka import Producer as KafkaProducer
from confluent_kafka.error import KafkaError

from app.instrumentation import message_not_produced
from app.logging import get_logger

# from app.instrumentation import message_produced

logger = get_logger(__name__)


def delivery_callback(err, msg):
    if err:
        # sys.stderr.write('%% Message failed delivery: %s\n' % err)
        # message_not_produced(logger, self.egress_topic, event, key, headers)
        # message_not_produced(logger, self.egress_topic, event, key, headers)
        logger.error("Message not produced.")

    else:
        # sys.stderr.write('%% Message delivered to %s [%d] @ %d\n' %
        # (msg.topic(), msg.partition(), msg.offset()))
        logger.info("Message produced!")


class EventProducer:
    def __init__(self, config):
        logger.info("Starting EventProducer()")
        # self._kafka_producer = KafkaProducer(bootstrap_servers=config.bootstrap_servers, **config.kafka_producer)
        self._kafka_producer = KafkaProducer({"bootstrap.servers": config.bootstrap_servers})
        self.egress_topic = config.event_topic

    def write_event(self, event, key, headers, *, wait=False):
        logger.debug("Topic: %s, key: %s, event: %s, headers: %s", self.egress_topic, key, event, headers)

        # k = key.encode("utf-8") if key else None
        v = event.encode("utf-8")
        # h = [(hk, (hv or "").encode("utf-8")) for hk, hv in headers.items()]

        try:
            # send_future = self._kafka_producer.send(self.egress_topic, key=k, value=v, headers=h)
            # send_future = self._kafka_producer.produce(self.egress_topic, v)
            send_future = self._kafka_producer.produce(self.egress_topic, v, callback=delivery_callback)
            self._kafka_producer.poll()
        except KafkaError as error:
            message_not_produced(logger, self.egress_topic, event, key, headers, error)
            raise error
            # else:
            #     # send_future.add_callback(message_produced, logger, event, key, headers)
            #     # send_future.add_errback(message_not_produced, logger, self.egress_topic, event, key, headers)

            #     message_produced(logger, event, key, headers)
            #     message_not_produced(logger, self.egress_topic, event, key, headers)

            if wait:
                send_future.get()

    def close(self):
        self._kafka_producer.flush()
        self._kafka_producer.close()

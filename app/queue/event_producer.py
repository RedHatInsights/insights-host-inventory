from enum import Enum

from kafka import KafkaProducer
from kafka.errors import KafkaError

from app.instrumentation import message_not_produced
from app.instrumentation import message_produced
from app.logging import get_logger

# from kafka.cluster import ClusterMetadata

logger = get_logger(__name__)

Topic = Enum("Topic", ("egress", "events"))


class EventProducer:
    def __init__(self, config):
        logger.info("Starting EventProducer()")
        # self._cluster_metadata = ClusterMetadata(bootstrap_servers=config.bootstrap_servers)
        self._kafka_producer = KafkaProducer(bootstrap_servers=config.bootstrap_servers, **config.kafka_producer)
        self.topics = {Topic.egress: config.host_egress_topic, Topic.events: config.event_topic}

    def write_event(self, event, key, headers, topic, *, wait=False, optionalCallback=None):
        logger.debug("Topic: %s, key: %s, event: %s, headers: %s", topic, key, event, headers)

        k = key.encode("utf-8") if key else None
        v = event.encode("utf-8")
        h = [(hk, (hv or "").encode("utf-8")) for hk, hv in headers.items()]

        try:
            send_future = self._kafka_producer.send(self.topics[topic], key=k, value=v, headers=h)
        except KafkaError as error:
            message_not_produced(logger, self.topics[topic], event, key, headers, error)
            raise error
        else:
            send_future.add_callback(message_produced, logger, event, key, headers)
            send_future.add_errback(message_not_produced, logger, self.topics[topic], event, key, headers)
            if optionalCallback:
                send_future.add_callback(optionalCallback)

            if wait:
                send_future.get()

    # def kafka_up(self):
    #     # #Check if kafka is running
    #     partitions = self._kafka_producer.partitions_for(self.topics[Topic.events])
    #     print(partitions)
    #     logger.info("partitions: %s",partitions)
    #     # connected = self._kafka_producer.bootstrap_connected() #doesn't work :(
    #     # logger.debug("connected: %s", connected)
    #     # self._cluster_metadata.update_metadata()
    #     topics = self._cluster_metadata.available_partitions_for_topic(self.topics[Topic.events])
    #     logger.debug("topics: %s", topics)
    #     # logger.debug("topics len: %s", len(topics))
    #     logger.debug("truthiness: %s", bool(topics))
    #     #Short circuit

    #     return False

    def close(self):
        self._kafka_producer.flush()
        self._kafka_producer.close()

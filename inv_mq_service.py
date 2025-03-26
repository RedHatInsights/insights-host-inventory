#!/usr/bin/python
from functools import partial

from confluent_kafka import Consumer as KafkaConsumer
from prometheus_client import start_http_server

from api.cache import init_cache
from app import create_app
from app.environment import RuntimeEnvironment
from app.logging import get_logger
from app.queue.event_producer import EventProducer
from app.queue.host_mq import HBIMessageConsumerBase
from app.queue.host_mq import IngressMessageConsumer
from app.queue.host_mq import SystemProfileMessageConsumer
from lib.handlers import ShutdownHandler
from lib.handlers import register_shutdown

logger = get_logger("host_mq_service")


def main():
    application = create_app(RuntimeEnvironment.SERVICE)
    config = application.app.config["INVENTORY_CONFIG"]
    init_cache(config, application)
    start_http_server(config.metrics_port)

    topic_to_hbi_consumer: dict[str, HBIMessageConsumerBase] = {
        config.host_ingress_topic: IngressMessageConsumer,
        config.system_profile_topic: SystemProfileMessageConsumer,
    }

    consumer = KafkaConsumer(
        {
            "group.id": config.host_ingress_consumer_group,
            "bootstrap.servers": config.bootstrap_servers,
            "auto.offset.reset": "earliest",
            **config.kafka_consumer,
        }
    )
    consumer.subscribe([config.kafka_consumer_topic])
    consumer_shutdown = partial(consumer.close, autocommit=True)
    register_shutdown(consumer_shutdown, "Closing consumer")

    event_producer = EventProducer(config, config.event_topic)
    register_shutdown(event_producer.close, "Closing producer")

    notification_event_producer = EventProducer(config, config.notification_topic)
    register_shutdown(notification_event_producer.close, "Closing notification producer")

    shutdown_handler = ShutdownHandler()
    shutdown_handler.register()

    hbi_consumer_class = topic_to_hbi_consumer[config.kafka_consumer_topic]
    hbi_consumer = hbi_consumer_class(consumer, application.app, event_producer, notification_event_producer)
    hbi_consumer.event_loop(shutdown_handler.shut_down)


if __name__ == "__main__":
    main()

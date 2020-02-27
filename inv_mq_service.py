import os
from signal import Signals

from kafka import KafkaConsumer
from prometheus_client import start_http_server

from app import create_app
from app.config import Config
from app.config import RuntimeEnvironment
from app.logging import get_logger
from app.queue.egress import create_event_producer
from app.queue.ingress import event_loop
from app.queue.ingress import handle_message

logger = get_logger("mq_service")


class ShutdownHandler:
    def __init__(self):
        self._shutdown = False

    def signal_handler(self, signum, frame):
        signame = Signals(signum).name
        logger.info("Gracefully Shutting Down. Received: %s", signame)
        self._shutdown = True

    def shut_down(self):
        return self._shutdown


def main():
    config_name = os.getenv("APP_SETTINGS", "development")
    application = create_app(config_name, start_tasks=False, start_payload_tracker=True)
    start_http_server(9126)

    config = Config(RuntimeEnvironment.server)

    consumer = KafkaConsumer(
        config.host_ingress_topic,
        group_id=config.host_ingress_consumer_group,
        bootstrap_servers=config.bootstrap_servers,
        api_version=(0, 10, 1),
        value_deserializer=lambda m: m.decode(),
        **config.kafka_consumer,
    )

    event_producer = create_event_producer(config, "kafka")

    try:
        event_loop(consumer, application, event_producer, handle_message, ShutdownHandler())
    finally:
        logger.info("Closing consumer")
        consumer.close(autocommit=True)
        logger.info("Closing producer")
        event_producer.close()


if __name__ == "__main__":
    main()

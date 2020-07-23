from kafka import KafkaConsumer
from prometheus_client import start_http_server

from app import create_app
from app.environment import RuntimeEnvironment
from app.logging import get_logger
from app.queue.event_producer import EventProducer
from app.queue.queue import event_loop
from app.queue.queue import handle_message

from lib.handlers import ShutdownHandler

logger = get_logger("mq_service")


def main():
    application = create_app(RuntimeEnvironment.SERVICE)
    start_http_server(9126)

    config = application.config["INVENTORY_CONFIG"]

    consumer = KafkaConsumer(
        config.host_ingress_topic,
        group_id=config.host_ingress_consumer_group,
        bootstrap_servers=config.bootstrap_servers,
        api_version=(0, 10, 1),
        value_deserializer=lambda m: m.decode(),
        **config.kafka_consumer,
    )

    event_producer = EventProducer(config)

    try:
        event_loop(consumer, application, event_producer, handle_message, ShutdownHandler())
    finally:
        logger.info("Closing consumer")
        consumer.close(autocommit=True)
        logger.info("Closing producer")
        event_producer.close()


if __name__ == "__main__":
    main()

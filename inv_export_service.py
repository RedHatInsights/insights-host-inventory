from functools import partial

from confluent_kafka import Consumer as KafkaConsumer
from prometheus_client import start_http_server

from app import create_app
from app.environment import RuntimeEnvironment
from app.logging import get_logger
from app.queue.queue import create_export
from app.queue.queue import event_loop
from app.queue.queue import handle_export_message
from lib.handlers import register_shutdown
from lib.handlers import ShutdownHandler

logger = get_logger("mq_service")


def main():
    application = create_app(RuntimeEnvironment.SERVICE)
    config = application.app.config["INVENTORY_CONFIG"]
    start_http_server(config.metrics_port)

    consumer = KafkaConsumer(
        {
            "group.id": config.inv_export_service_consumer_group,
            "bootstrap.servers": config.bootstrap_servers,
            "auto.offset.reset": "earliest",
            **config.kafka_consumer,
        }
    )
    consumer.subscribe([config.export_service_topic])
    consumer_shutdown = partial(consumer.close, autocommit=True)
    register_shutdown(consumer_shutdown, "Closing export service consumer")

    shutdown_handler = ShutdownHandler()
    shutdown_handler.register()

    message_handler = partial(
        handle_export_message,
        message_operation=create_export,
    )

    event_loop(
        consumer,
        application.app,
        None,
        None,
        message_handler,
        shutdown_handler.shut_down,
    )


if __name__ == "__main__":
    main()

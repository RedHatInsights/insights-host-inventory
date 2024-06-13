from functools import partial

from confluent_kafka import Consumer as KafkaConsumer
from prometheus_client import start_http_server

from app import create_app
from app.environment import RuntimeEnvironment
from app.logging import get_logger
from app.queue.queue import export_service_event_loop
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

    export_service_event_loop(
        consumer,
        application.app,
        shutdown_handler.shut_down,
    )


if __name__ == "__main__":
    main()

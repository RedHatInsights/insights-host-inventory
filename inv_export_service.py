#!/usr/bin/env python
import sys
import time
from functools import partial

from confluent_kafka import Consumer as KafkaConsumer
from prometheus_client import start_http_server

from app import create_app
from app.common import get_build_version
from app.environment import RuntimeEnvironment
from app.logging import get_logger
from app.queue.export_service_mq import ExportServiceConsumer
from app.telemetry import init_otel
from app.telemetry import instrument_kafka_consumer
from lib.handlers import ShutdownHandler
from lib.handlers import register_shutdown

logger = get_logger("export_sevice_mq")


def main():
    init_otel(service_name="host-inventory-export", service_version=get_build_version())

    application = create_app(RuntimeEnvironment.SERVICE)
    config = application.app.config["INVENTORY_CONFIG"]

    if config.replica_namespace:
        logger.info("Running in replica cluster - sleeping until shutdown")
        start_http_server(config.metrics_port)

        shutdown_handler = ShutdownHandler()
        shutdown_handler.register()

        while not shutdown_handler.shut_down():
            time.sleep(1)

        logger.info("Shutdown signal received, exiting gracefully")
        sys.exit(0)

    start_http_server(config.metrics_port)

    consumer = instrument_kafka_consumer(
        KafkaConsumer(
            {
                "group.id": config.inv_export_service_consumer_group,
                "bootstrap.servers": config.bootstrap_servers,
                **config.export_service_kafka_consumer,
            }
        )
    )
    consumer.subscribe([config.export_service_topic])
    consumer_shutdown = partial(consumer.close, autocommit=True)
    register_shutdown(consumer_shutdown, "Closing export service consumer")

    shutdown_handler = ShutdownHandler()
    shutdown_handler.register()

    logger.info(f"Using consumer topic: {config.export_service_topic}")
    export_consumer = ExportServiceConsumer(consumer, application, None, None)
    export_consumer.event_loop(shutdown_handler.shut_down)


if __name__ == "__main__":
    main()

import json
import os

from kafka import KafkaConsumer

from app import create_app
from app.config import Config
from app.exceptions import InventoryException, ValidationException
from app.logging import get_logger, threadctx
from app.queue.ingress import parse_operation_message
from app.queue import metrics
from lib import host
from prometheus_client import start_http_server


logger = get_logger("mq_service")


def add_host(host_data):
    try:
        logger.info("Attempting to add host...")
        host.add_host(host_data)
        logger.info("Host added") # This definitely needs to be more specific (added vs updated?)
    except InventoryException as e:
        logger.exception("Error adding host ", extra={"host": host_data})
        metrics.add_host_failure.inc()
    except Exception as e:
        logger.exception("Error while adding host", extra={"host": host_data})
        metrics.add_host_failure.inc()


def handle_message(message):
    validated_operation_msg = parse_operation_message(message)
    initialize_thread_local_storage(validated_operation_msg)
    # FIXME: verify operation type
    add_host(validated_operation_msg["data"])


def event_loop(consumer, flask_app, handler=handle_message):
    with flask_app.app_context():
        logger.debug("Waiting for message")
        for msg in consumer:
            logger.debug("Message received")
            try:
                handler(msg)
                metrics.ingress_message_handler_success.inc()
            except Exception:
                logger.exception("Unable to process message")


def initialize_thread_local_storage(operation_message):
    threadctx.request_id = operation_message.get("request_id", "-1")


def main():
    config_name = os.getenv('APP_SETTINGS', "development")
    application = create_app(config_name, start_tasks=False)
    start_http_server(9126)

    config = Config()

    consumer = KafkaConsumer(
        config.host_ingress_topic,
        group_id=config.host_ingress_consumer_group,
        bootstrap_servers=config.bootstrap_servers,
        api_version=(0,10))

    event_loop(consumer, application)

if __name__ == "__main__":
    main()

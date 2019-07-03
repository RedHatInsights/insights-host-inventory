import json
import os

from kafka import KafkaConsumer

from app import create_app
from app.config import Config
from app.exceptions import InventoryException, ValidationException
from app.logging import get_logger, threadctx
from lib import host
from inv_mq_parser import parse_operation_message


logger = get_logger("mq_service")


def add_host(host_data):
    try:
        logger.info("Attempting to add host...")
        host.add_host(host_data)
        logger.info("Host added") # This definitely needs to be more specific (added vs updated?)
    except InventoryException as e:
        logger.exception("Error adding host ", extra={"host": host_data})
    except Exception as e:
        logger.exception("Error while adding host", extra={"host": host_data})


def handle_message(message):
    try:
        validated_operation_msg = parse_operation_message(message)
    except ValidationException as e:
        logger.exception("Input validation error while parsing operation message", extra={"operation": message})
    else:
        initialize_thread_local_storage(validated_operation_msg)
        # FIXME: verify operation type
        add_host(validated_operation_msg["data"])


def event_loop(consumer, flask_app, handler=handle_message):
    with flask_app.app_context():
        logger.debug("Waiting for message")
        for msg in consumer:
            logger.debug("Message received")
            try:
                data = json.loads(msg.value)
            except Exception:
                # The "extra" dict cannot have a key named "msg" or "message"
                # otherwise an exception in thrown in the logging code
                logger.exception("Unable to parse json message from message queue",
                                 extra={"incoming_message": msg.value})
                continue

            try:
                handler(data)
            except Exception:
                logger.exception("Unable to process message")


def initialize_thread_local_storage(operation_message):
    threadctx.request_id = operation_message.get("request_id", "-1")


def main():
    config_name = os.getenv('APP_SETTINGS', "development")
    application = create_app(config_name, start_tasks=False)

    config = Config()

    consumer = KafkaConsumer(
        config.host_ingress_topic,
        group_id=config.host_ingress_consumer_group,
        bootstrap_servers=config.bootstrap_servers,
        api_version=(0,10))

    event_loop(consumer, application)

if __name__ == "__main__":
    main()

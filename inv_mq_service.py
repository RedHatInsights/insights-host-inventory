import json
import os

from kafka import KafkaConsumer

from marshmallow import Schema, fields, ValidationError

from app import create_app
from app.config import Config
from app.exceptions import InventoryException
from app.logging import get_logger, threadctx
from lib import host


logger = get_logger("mq_service")


class OperationSchema(Schema):
    operation = fields.Str()
    request_id = fields.Str()
    data = fields.Dict()


def parse_operation_message(message):
    try:
        return OperationSchema(strict=True).load(message).data
    except ValidationError as e:
        logger.exception("Input validation error while parsing operation message",
                         extra={"operation": message})
    except Exception as e:
        logger.exception("Error parsing operation message", extra={"operation": message})


def add_host(host_data):
    try:
        logger.info("Attempting to add host...")
        host.add_host(host_data)
        logger.info("Host added") # This definitely needs to be more specific (added vs updated?)
    except InventoryException as e:
        logger.exception("Error adding host ", extra={"host": host_data})
    # FIXME:  remove this.  the "library" should not expose implementation details like ValidationError
    except ValidationError as e:
        logger.exception("Input validation error while adding host",
                         extra={"host": host_data})
    except Exception as e:
        logger.exception("Error while adding host", extra={"host": host_data})


def handle_message(message):

    validated_operation_msg = parse_operation_message(message)

    initialize_thread_local_storage(validated_operation_msg)

    # FIXME: verify operation type

    add_host(validated_operation_msg["data"])


def event_loop(consumer, flask_app, handler=handle_message):
    with flask_app.app_context():
        while True:
            logger.debug("Waiting for message")
            for msg in consumer:
                logger.debug("Message received")
                try:
                    data = json.loads(msg.value)
                except Exception:
                    logger.exception("Unable to parse incoming host json data")

                handler(data)


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

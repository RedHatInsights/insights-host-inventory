import json
import os

from kafka import KafkaConsumer

# FIXME:  remove this
from marshmallow import ValidationError

from app import create_app
from app.config import Config
from app.exceptions import InventoryException
from app.logging import get_logger, threadctx
from lib.host import add_host


logger = get_logger("mq_service")


def handle_message(host):
    try:
        initialize_thread_local_storage(host)
        logger.info("Attempting to add host...")
        add_host(host)
        logger.info("Host added") # This definitely needs to be more specific (added vs updated?)
    except InventoryException as e:
        logger.exception("Error adding host", extra={"host": host})
    # FIXME:  remove this
    except ValidationError as e:
        logger.exception("Input validation error while adding host",
                         extra={"host": host})
    except Exception as e:
        logger.exception("Error adding host", extra={"host": host})


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


def initialize_thread_local_storage(host):
    threadctx.account_number = host["account"]
    threadctx.request_id = host.get("request_id", "-1")


def main():
    config_name = os.getenv('APP_SETTINGS', "development")
    application = create_app(config_name)

    config = Config()

    consumer = KafkaConsumer(
        config.host_ingress_topic,
        group_id=config.host_ingress_consumer_group,
        bootstrap_servers=config.bootstrap_servers,
        api_version=(0,10))

    event_loop(consumer, application)

if __name__ == "__main__":
    main()

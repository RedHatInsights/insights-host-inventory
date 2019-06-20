import json
import logging
import os

from kafka import KafkaConsumer

# FIXME:  remove this
from marshmallow import ValidationError

from app import create_app
from app.config import Config
from app.exceptions import InventoryException
from lib.host import add_host


logger = logging.getLogger("inventory_mq_service")


def handle_message(host):
    try:
        add_host(host)
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
            print("waiting for msg")
            for msg in consumer:
                print("got a msg")
                try:
                    data = json.loads(msg.value)
                except Exception:
                    logger.exception("Unable to parse incoming host json data")

                handler(data)


def main():
    logging.basicConfig(level=logging.INFO)
    config_name = os.getenv('APP_SETTINGS', "development")
    application = create_app(config_name)

    config = Config()
    config.log_configuration(config_name)

    print("host_ingress_topic:", config.host_ingress_topic)
    print("consumer_group:", config.consumer_group)
    print("bootstrap_servers:", config.bootstrap_servers)

    consumer = KafkaConsumer(
        config.host_ingress_topic,
        group_id=config.consumer_group,
        bootstrap_servers=config.bootstrap_servers)

    event_loop(consumer, application)

if __name__ == "__main__":
    main()

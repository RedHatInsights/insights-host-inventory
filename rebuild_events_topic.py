import json
import sys
from functools import partial

from kafka import KafkaConsumer
from kafka import TopicPartition
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app import create_app
from app.environment import RuntimeEnvironment
from app.logging import configure_logging
from app.logging import get_logger
from app.logging import threadctx
from app.queue.event_producer import EventProducer
from app.queue.queue import sync_event_message
from lib.db import session_guard
from lib.handlers import register_shutdown
from lib.handlers import ShutdownHandler

# from prometheus_client import start_http_server


__all__ = "main"

LOGGER_NAME = "inventory_events_rebuilder"


def _excepthook(logger, type, value, traceback):
    logger.exception("Events topic rebuilder failed", exc_info=value)


def _init_db(config):
    engine = create_engine(config.db_uri)
    return sessionmaker(bind=engine)


def run(config, logger, session, consumer, event_producer, shutdown_handler):
    num_messages = 1
    partitions = []

    # Seek to beginning
    logger.debug(f"Partitions for topic {config.event_topic}:")
    logger.debug(consumer.partitions_for_topic(config.event_topic))
    for partition_id in consumer.partitions_for_topic(config.event_topic):
        logger.debug(f"Appending partition {partition_id} for topic: {config.event_topic}")
        partitions.append(TopicPartition(config.event_topic, partition_id))

    consumer.assign(partitions)
    partitions = consumer.assignment()
    consumer.seek_to_beginning(*partitions)
    total_messages_processed = 0

    logger.debug("About to start the consumer loop")
    while num_messages > 0:
        logger.debug("Entered first loop")
        num_messages = 0
        for partition, messages in consumer.poll(timeout_ms=60000, max_records=500).items():
            logger.debug("Entered second loop")
            for message in messages:
                logger.debug("Message received")
                try:
                    sync_event_message(json.loads(message.value), session, event_producer)
                    # TODO: Metrics
                    # metrics.ingress_message_handler_success.inc()
                except OperationalError as oe:
                    """sqlalchemy.exc.OperationalError: This error occurs when an
                    authentication failure occurs or the DB is not accessible.
                    """
                    logger.error(f"Could not access DB {str(oe)}")
                    sys.exit(3)
                except Exception:
                    # TODO: Metrics
                    # metrics.ingress_message_handler_failure.inc()
                    logger.exception("Unable to process message", extra={"incoming_message": message.value})

            num_messages += len(messages)

        total_messages_processed += num_messages

    logger.info(f"Event topic rebuild complete. Processed {total_messages_processed} messages.")


def main(logger):
    application = create_app(RuntimeEnvironment.JOB)
    config = application.config["INVENTORY_CONFIG"]
    Session = _init_db(config)
    session = Session()
    # TODO: Metrics
    # start_http_server(config.metrics_port)

    consumer = KafkaConsumer(
        bootstrap_servers=config.bootstrap_servers,
        api_version=(0, 10, 1),
        value_deserializer=lambda m: m.decode(),
        **config.events_kafka_consumer,
    )

    register_shutdown(session.get_bind().dispose, "Closing database")
    consumer_shutdown = partial(consumer.close, autocommit=True)
    register_shutdown(consumer_shutdown, "Closing consumer")
    event_producer = EventProducer(config, config.event_topic)
    register_shutdown(event_producer.close, "Closing producer")
    shutdown_handler = ShutdownHandler()
    shutdown_handler.register()

    with session_guard(session):
        run(config, logger, session, consumer, event_producer, shutdown_handler)


if __name__ == "__main__":
    configure_logging()

    logger = get_logger(LOGGER_NAME)
    sys.excepthook = partial(_excepthook, logger)

    threadctx.request_id = None
    main(logger)

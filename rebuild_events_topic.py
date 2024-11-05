#!/usr/bin/python
import json
import sys
from datetime import datetime
from datetime import timedelta
from functools import partial

from confluent_kafka import Consumer as KafkaConsumer
from confluent_kafka import TopicPartition
from confluent_kafka.error import ProduceError
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app import create_app
from app.environment import RuntimeEnvironment
from app.logging import configure_logging
from app.logging import get_logger
from app.logging import threadctx
from app.queue.event_producer import EventProducer
from app.queue.host_mq import sync_event_message
from lib.db import session_guard
from lib.handlers import ShutdownHandler
from lib.handlers import register_shutdown

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
    filtered_topics = consumer.list_topics(config.event_topic)
    partitions_dict = filtered_topics.topics[config.event_topic].partitions
    for partition_id in partitions_dict.keys():
        logger.debug(f"Partition ID: {partition_id}:")
        # Confluent-Kafka has not implemented seekToBeginning, so we're required
        # to use the internal value for the beginning, which is -2.
        partitions.append(TopicPartition(config.event_topic, partition_id, -2))

    consumer.assign(partitions)
    partitions = consumer.assignment()
    total_messages_processed = 0

    stop_time = datetime.now() + timedelta(seconds=config.rebuild_events_time_limit)
    logger.debug("About to start the consumer loop")
    while num_messages > 0 and not shutdown_handler.shut_down():
        if datetime.now() > stop_time:
            logger.info(f"Event topic rebuild halting after {config.rebuild_events_time_limit} seconds time.")
            exit(0)  # exit as intended

        new_messages = consumer.consume(num_messages=config.script_chunk_size, timeout=10)
        with session_guard(session):
            for message in new_messages:
                try:
                    sync_event_message(json.loads(message.value()), session, event_producer)

                except OperationalError as oe:
                    """sqlalchemy.exc.OperationalError: This error occurs when an
                    authentication failure occurs or the DB is not accessible.
                    """
                    logger.error(f"Could not access DB {str(oe)}")
                    sys.exit(3)
                except Exception:
                    logger.exception("Unable to process message", extra={"incoming_message": message.value()})
        try:
            # pace the events production speed as flush completes sending all buffered records.
            event_producer._kafka_producer.flush(300)
        except ProduceError as e:
            raise ProduceError("ProduceError: Failed to flush produced Kafka messages within 300 seconds") from e

        num_messages = len(new_messages)
        total_messages_processed += num_messages

    logger.info(f"Event topic rebuild complete. Processed {total_messages_processed} messages.")


def main(logger):
    application = create_app(RuntimeEnvironment.JOB)
    config = application.app.config["INVENTORY_CONFIG"]
    Session = _init_db(config)
    session = Session()
    # TODO: Metrics
    # start_http_server(config.metrics_port)

    consumer = KafkaConsumer(
        {
            "bootstrap.servers": config.bootstrap_servers,
            **config.events_kafka_consumer,
        }
    )

    register_shutdown(session.get_bind().dispose, "Closing database")
    consumer_shutdown = partial(consumer.close, autocommit=True)
    register_shutdown(consumer_shutdown, "Closing consumer")
    event_producer = EventProducer(config, config.event_topic)
    register_shutdown(event_producer.close, "Closing producer")
    shutdown_handler = ShutdownHandler()
    shutdown_handler.register()

    run(config, logger, session, consumer, event_producer, shutdown_handler)


if __name__ == "__main__":
    configure_logging()

    logger = get_logger(LOGGER_NAME)
    sys.excepthook = partial(_excepthook, logger)

    threadctx.request_id = None
    main(logger)

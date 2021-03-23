from functools import partial

from kafka import KafkaConsumer
from prometheus_client import start_http_server

from app import create_app
from app.environment import RuntimeEnvironment
from app.logging import get_logger
from app.queue.event_producer import EventProducer
from app.queue.queue import add_host
from app.queue.queue import event_loop
from app.queue.queue import handle_message
from app.queue.queue import update_system_profile
from lib.handlers import register_shutdown
from lib.handlers import ShutdownHandler

logger = get_logger("mq_service")

field_restriction_to_handler = {{"ALL": add_host}, {"SYSTEM_PROFILE": update_system_profile}}


def main():
    application = create_app(RuntimeEnvironment.SERVICE)
    config = application.config["INVENTORY_CONFIG"]
    start_http_server(config.metrics_port)

    consumer = KafkaConsumer(
        config.host_ingress_topic,
        group_id=config.host_ingress_consumer_group,
        bootstrap_servers=config.bootstrap_servers,
        api_version=(0, 10, 1),
        value_deserializer=lambda m: m.decode(),
        **config.kafka_consumer,
    )
    consumer_shutdown = partial(consumer.close, autocommit=True)
    register_shutdown(consumer_shutdown, "Closing consumer")

    event_producer = EventProducer(config)
    register_shutdown(event_producer.close, "Closing producer")

    shutdown_handler = ShutdownHandler()
    shutdown_handler.register()

    message_handler = partial(
        handle_message, host_operation=field_restriction_to_handler.get(config.mq_restrict_to_field, add_host)
    )

    event_loop(consumer, application, event_producer, message_handler, shutdown_handler.shut_down)


if __name__ == "__main__":
    main()

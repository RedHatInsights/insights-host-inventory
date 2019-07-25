import os

from kafka import KafkaConsumer

from app import create_app
from app.config import Config
from app.logging import get_logger
from app.queue.ingress import event_loop
from prometheus_client import start_http_server

logger = get_logger("mq_service")

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

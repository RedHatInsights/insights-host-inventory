import json
import logging
import os

from confluent_kafka import Consumer as KafkaConsumer

# from app.models import Host
# from app.models import SystemProfileSchema


EVENTS_TOPIC = os.environ.get("KAFKA_EVENT_TOPIC", "platform.inventory.events")
HOST_INGRESS_GROUP = os.environ.get("KAFKA_HOST_INGRESS_GROUP", "inventory-mq")
BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")


def msg_handler(parsed):
    print("inside msg_handler()")
    print("type(parsed):", type(parsed))
    print("parsed:", parsed)
    # id_ = parsed["id"]
    # profile = SystemProfileSchema(strict=True).load(parsed["system_profile"])
    # host = Host.query.get(id_)
    # host._update_system_profile(profile)
    # host.save()


def main():
    consumer = KafkaConsumer(EVENTS_TOPIC, group_id=HOST_INGRESS_GROUP, bootstrap_servers=BOOTSTRAP_SERVERS)

    logging.basicConfig(level=logging.INFO)

    print("EVENTS_TOPIC:", EVENTS_TOPIC)
    print("KAFKA_HOST_INGRESS_GROUP:", HOST_INGRESS_GROUP)
    print("BOOTSTRAP_SERVERS:", BOOTSTRAP_SERVERS)

    for msg in consumer:
        print("calling msg_handler()")
        print("Message Headers:", msg.headers)
        msg_handler(json.loads(msg.value))


if __name__ == "__main__":
    main()

import os
import json
from kafka import KafkaConsumer
from threading import Thread

# from app.models import Host, SystemProfileSchema

import logging


TOPIC = os.environ.get("KAFKA_TOPIC", "platform.inventory.host-egress")
KAFKA_GROUP = os.environ.get("KAFKA_GROUP", "inventory-mq")
BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")


def msg_handler(parsed):
    print("type(parsed):", type(parsed))
    print("inside msg_handler()")
    print("parsed:", parsed)
    # id_ = parsed["id"]
    # profile = SystemProfileSchema(strict=True).load(parsed["system_profile"])
    # host = Host.query.get(id_)
    # host._update_system_profile(profile)
    # host.save()


consumer = KafkaConsumer(
    TOPIC, group_id=KAFKA_GROUP, bootstrap_servers=BOOTSTRAP_SERVERS
)

# logging.basicConfig(level=logging.DEBUG)

print("TOPIC:", TOPIC)
print("KAFKA_GROUP:", KAFKA_GROUP)
print("BOOTSTRAP_SERVERS:", BOOTSTRAP_SERVERS)

print("msg in consumer")
print("consumer:", consumer)
print("type(consumer):", type(consumer))
for msg in consumer:
    print("entering handler()")
    msg_handler(json.loads(msg.value))

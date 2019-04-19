import os
import json
from kafka import KafkaConsumer
from threading import Thread

from app.models import Host

TOPIC = os.environ.get("KAFKA_TOPIC")
KAFKA_GROUP = os.environ.get("KAFKA_GROUP", "inventory")
BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")


def msg_handler(msg):
    parsed = json.loads(msg.value)
    # validate here?
    id_ = parsed["id"]
    host = Host.query.get(id_)
    host._update_system_profile(
        parsed["system_profile"]
    )
    host.save()


def start_consumer(handler, consumer=None):

    if consumer is None:
        consumer = KafkaConsumer(
            TOPIC,
            group_id=KAFKA_GROUP,
            bootstrap_servers=BOOTSTRAP_SERVERS)

    def _f():
        # TODO: plan for graceful exit
        #       and consumer failure/reconnect
        while True:
            for msg in consumer:
                handler(msg)

    t = Thread(
        target=_f,
        daemon=True)
    t.start()

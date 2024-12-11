import logging
import os
import sys

import payloads
from confluent_kafka import Producer as KafkaProducer

HOST_INGRESS_TOPIC = os.environ.get("KAFKA_HOST_INGRESS_TOPIC", "platform.inventory.host-ingress")
BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")
NUM_HOSTS = int(os.environ.get("NUM_HOSTS", 1))


def main():
    # Create list of host payloads to add to the message queue
    # payloads.build_payloads takes two optional args: number of hosts, and payload type ("default", "rhsm", "qpc")
    all_payloads = [payloads.build_mq_payload() for _ in range(NUM_HOSTS)]
    print("Number of hosts (payloads): ", len(all_payloads))

    producer = KafkaProducer({"bootstrap.servers": BOOTSTRAP_SERVERS})
    print("HOST_INGRESS_TOPIC:", HOST_INGRESS_TOPIC)

    def delivery_callback(err, msg):
        if err:
            sys.stderr.write(f"% Message failed delivery: {err}\n")
        else:
            sys.stderr.write(f"% Message delivered to {msg.topic()} [{msg.partition()}] @ {msg.offset()}\n")

    for payload in all_payloads:
        producer.produce(HOST_INGRESS_TOPIC, value=payload, callback=delivery_callback)
    producer.flush()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()

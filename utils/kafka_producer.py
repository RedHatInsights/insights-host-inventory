import logging
import os
import sys

import payloads
from confluent_kafka import Producer as KafkaProducer
from ttictoc import TicToc


HOST_INGRESS_TOPIC = os.environ.get("KAFKA_HOST_INGRESS_TOPIC", "platform.inventory.host-ingress")
BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")
NUM_HOSTS = int(os.environ.get("NUM_HOSTS", 5))


def main():
    # Create list of host payloads to add to the message queue
    # payloads.build_payloads takes two optional args: number of hosts, and payload type ("default", "rhsm", "qpc")
    with TicToc("Build payloads"):
        all_payloads = [payloads.build_mq_payload() for _ in range(NUM_HOSTS)]
    print("Number of hosts (payloads): ", len(all_payloads))

    producer = KafkaProducer({"bootstrap.servers": BOOTSTRAP_SERVERS})
    print("HOST_INGRESS_TOPIC:", HOST_INGRESS_TOPIC)

    def delivery_callback(err, msg):
        if err:
            sys.stderr.write("%% Message failed delivery: %s\n" % err)
        else:
            sys.stderr.write("%% Message delivered to %s [%d] @ %d\n" % (msg.topic(), msg.partition(), msg.offset()))

    with TicToc("Send all hosts to queue"):
        for payload in all_payloads:
            producer.produce(HOST_INGRESS_TOPIC, value=payload, callback=delivery_callback)
    producer.flush()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()

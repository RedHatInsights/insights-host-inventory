import logging
import os
import time

import payloads
from kafka import KafkaProducer

logging.basicConfig(level=logging.INFO)

HOST_INGRESS_TOPIC = os.environ.get("KAFKA_HOST_INGRESS_TOPIC", "platform.inventory.host-ingress")
BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")

# payload = payloads.build_chunk()

# Create list of host payloads to add to the message queue
# payloads.build_payloads takes two optional args: number of hosts, and payload type ("default", "rhsm", "qpc")
start = time.time()
all_payloads = payloads.build_payloads()  # pass in the number of hosts you'd like to send (defaults to 1)
end = time.time()
print("time elapsed to build payloads: ", end - start)
print("Number of hosts (payloads): ", len(all_payloads))

producer = KafkaProducer(bootstrap_servers=BOOTSTRAP_SERVERS, api_version=(0, 10))
print("HOST_INGRESS_TOPIC:", HOST_INGRESS_TOPIC)

start = time.time()
for payload in all_payloads:
    producer.send(HOST_INGRESS_TOPIC, value=payload)
producer.flush()
end = time.time()
print("Time to send all hosts to queue: ", end - start)

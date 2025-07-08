import logging
import os
import sys
import time

from confluent_kafka.admin import AdminClient

import payloads
from confluent_kafka import Producer as KafkaProducer, TopicPartition, ConsumerGroupTopicPartitions, Consumer

from app import create_app
from app.environment import RuntimeEnvironment
from app.models import Host

HOST_INGRESS_TOPIC = os.environ.get("KAFKA_HOST_INGRESS_TOPIC", "platform.inventory.host-ingress")
BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")
CONSUMER_GROUP = "inventory-mq"
NUM_HOSTS = int(os.environ.get("NUM_HOSTS", 1))
USE_EXISTING_HOSTS = os.environ.get("USE_EXISTING_HOSTS", "false").lower() == "true"

admin_client = AdminClient({'bootstrap.servers': BOOTSTRAP_SERVERS})
consumer = Consumer({'bootstrap.servers': BOOTSTRAP_SERVERS, 'group.id': 'fake'})


def main():
    if USE_EXISTING_HOSTS:
        application = create_app(RuntimeEnvironment.COMMAND)
        with application.app.app_context():
            canonical_facts_list = Host.query.with_entities(
                Host.canonical_facts,
                Host.org_id
            ).limit(NUM_HOSTS).all()
            # The ratio of updates to inserts in prod is about 100 to 1.  For every 100 updated systems, add a new system
            all_payloads = [payloads.build_mq_payload(canonical_facts = canonical_facts_list[i] if i % 100 != 0 else None) for i in range(NUM_HOSTS)]

    else:
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
    wait_for_processing_complete()
    consumer.close()


def get_consumer_lag():
    group_request = ConsumerGroupTopicPartitions(CONSUMER_GROUP)
    committed_tp = admin_client.list_consumer_group_offsets([group_request])[CONSUMER_GROUP].result().topic_partitions[0]
    _, high_offset = consumer.get_watermark_offsets(committed_tp, timeout=1)
    return max(0, high_offset - committed_tp.offset)

def wait_for_processing_complete():
    start_time = time.time()

    while True:
        lag = get_consumer_lag()
        print(lag)
        if lag == 0:
            break
        time.sleep(0.5)

    print("Duration: ", time.time() - start_time)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()

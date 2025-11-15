# kafka-python way of creating a topic
from confluent_kafka.admin import AdminClient
from confluent_kafka.cimpl import NewTopic

admin_client = AdminClient({"bootstrap.servers": "kafkahost:9092"})

new_topics = [NewTopic("example_topic", num_partitions=1, replication_factor=1)]

future = admin_client.create_topics(new_topics)

for _, f in future.items():
    try:
        f.result()
        print("Topic created")
    except Exception:
        print("Failed to create topic")

from prometheus_client import Counter

# from prometheus_client import Summary

payload_tracker_message_send_failure = Counter(
    "inventory_payload_tracker_message_send_failure_count", "Count of failures to send message to the payload tracker"
)
payload_tracker_message_construction_failure = Counter(
    "inventory_payload_tracker_message_construction_failure_count", "Count of failures to send to the payload tracker"
)

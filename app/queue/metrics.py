from prometheus_client import Counter
from prometheus_client import Info
from prometheus_client import Summary

from app.common import get_build_version

ingress_message_parsing_time = Summary(
    "inventory_ingress_message_parsing_seconds", "Time spent parsing a message from the ingress queue"
)
ingress_message_parsing_failure = Counter(
    "inventory_ingress_message_parsing_failures", "Total amount of failures parsing ingress messages"
)
add_host_success = Counter("inventory_ingress_add_host_successes", "Total amount of successfully added hosts")
add_host_failure = Counter("inventory_ingress_add_host_failures", "Total amount of failures adding hosts")
ingress_message_handler_success = Counter(
    "inventory_ingress_message_handler_successes",
    "Total amount of successfully handled messages from the ingress queue",
)
ingress_message_handler_failure = Counter(
    "inventory_ingress_message_handler_failures", "Total amount of failures handling messages from the ingress queue"
)
ingress_message_handler_time = Summary(
    "inventory_ingress_message_handler_seconds", "Total time spent handling messages from the ingress queue"
)
version = Info("inventory_mq_service_version", "Build version for the inventory message queue service")
version.info({"version": get_build_version()})
egress_message_handler_success = Counter(
    "inventory_egress_message_handler_successes", "Total amount of messages successfully written to the egress queue"
)
egress_message_handler_failure = Counter(
    "inventory_egress_message_handler_failures", "Total amount of failures while writing messages to the egress queue"
)
egress_event_serialization_time = Summary(
    "inventory_egress_event_serialization_seconds", "Time spent parsing a message from the egress queue"
)

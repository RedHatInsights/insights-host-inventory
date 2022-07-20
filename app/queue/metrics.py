from prometheus_client import Counter
from prometheus_client import Info
from prometheus_client import Summary

from app.common import get_build_version

ingress_message_parsing_time = Summary(
    "inventory_ingress_message_parsing_seconds", "Time spent parsing a message from the ingress queue"
)
ingress_message_parsing_failure = Counter(
    "inventory_ingress_message_parsing_failures", "Total amount of failures parsing ingress messages", ["cause"]
)
add_host_success = Counter(
    "inventory_ingress_add_host_successes", "Total amount of successfully added hosts", ["result", "reporter"]
)
add_host_failure = Counter(
    "inventory_ingress_add_host_failures", "Total amount of failures adding hosts", ["cause", "reporter"]
)
update_system_profile_success = Counter(
    "inventory_ingress_update_system_profile_successes", "Total amount of successfully updated system profiles"
)
update_system_profile_failure = Counter(
    "inventory_ingress_update_system_profile_failures", "Total amount of failures updating system profiles", ["cause"]
)
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
event_producer_success = Counter(
    "inventory_event_producer_successes", "Total amount of messages successfully written", ["event_type", "topic"]
)
event_producer_failure = Counter(
    "inventory_event_producer_failures", "Total amount of failures while writing messages", ["event_type", "topic"]
)
event_serialization_time = Summary(
    "inventory_event_serialization_seconds", "Time spent parsing a message", ["event_type"]
)
notification_event_producer_success = Counter(
    "notification_event_producer_successes",
    "Total amount of messages successfully written",
    ["notification_type", "topic"],
)
notification_event_producer_failure = Counter(
    "notification_event_producer_failures",
    "Total amount of failures while writing messages",
    ["notification_type", "topic"],
)
notification_event_serialization_time = Summary(
    "notification_event_serialization_seconds", "Time spent parsing a message", ["notification_type"]
)
rbac_fetching_failure = Counter("inventory_rbac_fetching_failures", "Total amount of failures fetching RBAC data")
rbac_access_denied = Counter(
    "inventory_rbac_access_denied", "Total amount of failures authorizing with RBAC", ["required_permission"]
)
tenant_translator_fetching_failure = Counter(
    "inventory_tenant_translator_fetching_failures", "Total amount of failures fetching 3scale tenant translator data"
)
db_communication_error = Counter(
    "inventory_mq_db_communication_error",
    "Total number of connection errors between inventory-mq and the DB",
    ["id", "reporter"],
)

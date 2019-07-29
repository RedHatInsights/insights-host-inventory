from prometheus_client import Counter
from prometheus_client import Summary

api_request_time = Summary("inventory_request_processing_seconds", "Time spent processing request")
api_request_count = Counter("inventory_request_count", "The total amount of API requests")
delete_host_count = Counter("inventory_delete_host_count", "The total amount of hosts deleted")
delete_host_processing_time = Summary(
    "inventory_delete_host_commit_seconds", "Time spent deleting hosts from the database"
)
login_failure_count = Counter("inventory_login_failure_count",
                              "The total amount of failed login attempts")
system_profile_deserialization_time = Summary(
    "inventory_system_profile_deserialization_time", "Time spent deserializing system profile documents"
)
system_profile_commit_processing_time = Summary(
    "inventory_system_profile_commit_processing_time",
    "Time spent committing an update to a system profile to the database",
)
system_profile_commit_count = Counter(
    "inventory_system_profile_commit_count", "Count of successful system profile commits to the database"
)
system_profile_failure_count = Counter(
    "inventory_system_profile_failure_count", "Count of failures to commit the system profile to the database"
)

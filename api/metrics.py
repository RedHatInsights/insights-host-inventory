from prometheus_client import Counter, Summary

api_request_time = Summary("inventory_request_processing_seconds", "Time spent processing request")
create_host_count = Counter("inventory_create_host_count", "The total amount of hosts created")
update_host_count = Counter("inventory_update_host_count", "The total amount of hosts updated")

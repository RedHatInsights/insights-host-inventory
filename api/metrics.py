from prometheus_client import Counter, Summary

api_request_time = Summary("inventory_request_processing_seconds", "Time spent processing request")
api_request_count = Counter("inventory_request_count", "The total amount of API requests")
create_host_count = Counter("inventory_create_host_count", "The total amount of hosts created")
update_host_count = Counter("inventory_update_host_count", "The total amount of hosts updated")
merge_facts_count = Counter("inventory_merge_facts_count", "The total amount of facts merged")
replace_facts_count = Counter("inventory_replace_facts_count", "The total amount of facts replaced")

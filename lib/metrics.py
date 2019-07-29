from prometheus_client import Counter
from prometheus_client import Summary

host_dedup_processing_time = Summary(
    "inventory_dedup_processing_seconds", "Time spent looking for existing host (dedup logic)"
)
find_host_using_elevated_ids = Summary(
    "inventory_find_host_using_elevated_ids_processing_seconds",
    "Time spent looking for existing host using the elevated ids",
)
new_host_commit_processing_time = Summary(
    "inventory_new_host_commit_seconds", "Time spent committing a new host to the database"
)
update_host_commit_processing_time = Summary(
    "inventory_update_host_commit_seconds", "Time spent committing a update host to the database"
)
create_host_count = Counter("inventory_create_host_count", "The total amount of hosts created")
update_host_count = Counter("inventory_update_host_count", "The total amount of hosts updated")

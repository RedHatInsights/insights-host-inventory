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
delete_host_count = Counter("inventory_delete_host_count", "The total amount of hosts deleted")
delete_host_processing_time = Summary(
    "inventory_delete_host_commit_seconds", "Time spent deleting hosts from the database"
)
host_reaper_fail_count = Counter("inventory_reaper_fail_count", "The total amount of Host Reaper failures.")

# Inventory Groups
create_group_count = Counter("inventory_create_group_count", "The total amount of groups created")
update_group_count = Counter("inventory_update_group_count", "The total amount of groups updated")
delete_group_count = Counter("inventory_delete_group_count", "The total amount of groups deleted")
delete_group_processing_time = Summary(
    "inventory_delete_group_commit_seconds", "Time spent deleting groups from the database"
)

create_host_group_count = Counter("inventory_create_host_group_count", "The total amount of host-groups created")
update_host_group_count = Counter("inventory_update_host_group_count", "The total amount of host_groups updated")
delete_host_group_count = Counter("inventory_delete_host_group_count", "The total amount of host_groups deleted")
delete_host_group_processing_time = Summary(
    "inventory_delete_host_group_commit_seconds", "Time spent deleting host-groups from the database"
)

# synchronization counter
synchronize_host_count = Counter("inventory_synchronize_host_count", "The total amount of hosts synchronized")
synchronize_fail_count = Counter("inventory_synchronize_fail_count", "The total amount of synchronization failures")

pendo_fetching_failure = Counter(
    "inventory_pendo_syncher_failures", "Total amount of failures while sending Pendo data"
)

delete_duplicate_host_count = Counter("inventory_delete_duplicate_host_count", "The total amount of hosts deleted")

# Export Service
create_export_processing_time = Summary(
    "inventory_new_export_seconds", "Time spent to create a new host export report"
)
create_export_count = Counter("inventory_create_export", "The total amount of host exports created")

# hosts-syndication counter
hosts_syndication_fail_count = Counter(
    "hosts_syndication_fail_count", "The total number of syndication attempts failed."
)
hosts_syndication_success_count = Counter(
    "hosts_syndication_success_count", "The total number of syndication attempts succeeded."
)
hosts_syndication_time = Summary("hosts_syndication_time", "The time syndication performed")

# Stale Host Notification
stale_host_notification_success_count = Counter(
    "inventory_stale_host_notification_success_count",
    "The total amount of stale hosts notifications produced successfully",
)
stale_host_notification_processing_time = Summary(
    "inventory_stale_host_notification_processing_time", "Time spent generating stale host notifications"
)
stale_host_notification_fail_count = Counter(
    "inventory_stale_host_notification_fail_count", "The total amount of Stale Host Notification failures."
)

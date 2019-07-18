from prometheus_client import Counter, Summary

api_request_time = Summary("inventory_request_processing_seconds",
                           "Time spent processing request")
host_dedup_processing_time = Summary("inventory_dedup_processing_seconds",
                                     "Time spent looking for existing host (dedup logic)")
find_host_using_elevated_ids = Summary("inventory_find_host_using_elevated_ids_processing_seconds",
                                       "Time spent looking for existing host using the elevated ids")
new_host_commit_processing_time = Summary("inventory_new_host_commit_seconds",
                                          "Time spent committing a new host to the database")
update_host_commit_processing_time = Summary("inventory_update_host_commit_seconds",
                                             "Time spent committing a update host to the database")
api_request_count = Counter("inventory_request_count",
                            "The total amount of API requests")
create_host_count = Counter("inventory_create_host_count",
                            "The total amount of hosts created")
update_host_count = Counter("inventory_update_host_count",
                            "The total amount of hosts updated")
delete_host_count = Counter("inventory_delete_host_count",
                            "The total amount of hosts deleted")
delete_host_processing_time = Summary("inventory_delete_host_commit_seconds",
                                      "Time spent deleting hosts from the database")
login_failure_count = Counter("inventory_login_failure_count",
                              "The total amount of failed login attempts")
system_profile_deserialization_time = Summary("inventory_system_profile_deserialization_time",
                                              "Time spent deserializing system profile documents")
system_profile_commit_processing_time = Summary("inventory_system_profile_commit_processing_time",
                                                "Time spent committing an update to a system profile to the database")
system_profile_commit_count = Counter("inventory_system_profile_commit_count",
                                      "Count of successful system profile commits to the database")
system_profile_failure_count = Counter("inventory_system_profile_failure_count",
                                       "Count of failures to commit the system profile to the database")

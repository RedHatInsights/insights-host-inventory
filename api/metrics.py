from prometheus_client import Counter, Summary

api_request_time = Summary("inventory_request_processing_seconds",
                           "Time spent processing request")
host_dedup_processing_time = Summary("inventory_dedup_processing_seconds",
                                     "Time spent looking for existing host (dedup logic)")
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
login_failure_count = Counter("inventory_login_failure_count",
                              "The total amount of failed login attempts")

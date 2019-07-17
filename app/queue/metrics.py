from prometheus_client import Counter, Summary

ingress_message_parsing_time = Summary("inventory_ingress_message_parsing_seconds",
                                                "Time spent parsing a message from the ingress queue")
ingress_message_parsing_failure = Counter("inventory_ingress_message_parsing_failures",
                                                "Total amount of failures parsing ingress messages")
add_host_failure = Counter("inventory_add_host_failures", "Total amount of failures adding hosts")
ingress_message_handler_success = Counter("inventory_ingress_message_handler_successes",
                                                "Total amount of successfully handled messages from the ingress queue")
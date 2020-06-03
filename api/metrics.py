from prometheus_client import Counter
from prometheus_client import Summary

api_request_time = Summary("inventory_request_processing_seconds", "Time spent processing request")
api_request_count = Counter("inventory_request_count", "The total amount of API requests")
login_failure_count = Counter("inventory_login_failure_count", "The total amount of failed login attempts")
tags_ignored_from_http_count = Counter(
    "inventory_tags_ignored_from_http_count", "Number of times we have ignored tags sent through HTTP"
)

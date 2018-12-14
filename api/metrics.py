from functools import wraps
from prometheus_client import Counter, Summary

api_request_time = Summary("inventory_request_processing_seconds", "Time spent processing request")
api_request_count = Counter("inventory_request_count", "The total amount of API requests")
create_host_count = Counter("inventory_create_host_count", "The total amount of hosts created")
update_host_count = Counter("inventory_update_host_count", "The total amount of hosts updated")


def count_inc(counter):
    """
    Creates a decorator that increates the given counter on every function call.
    """
    def decorator(old_function):
        """
        Decorates the function so it increases the counter on each call.
        """
        @wraps(old_function)
        def new_function(*args, **kwargs):
            """
            Increases the counter and calls the original function.
            """
            counter.inc()
            return old_function(*args, **kwargs)
        return new_function
    return decorator

from functools import wraps

from api.metrics import api_request_count

__all__ = ["api_operation"]


def api_operation(old_func):
    """
    Marks an API request operation. This means:
    * API request counter is incremented on every call.
    """

    @wraps(old_func)
    def new_func(*args, **kwargs):
        api_request_count.inc()
        return old_func(*args, **kwargs)

    return new_func

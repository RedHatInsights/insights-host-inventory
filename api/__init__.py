import logging
import time

from functools import wraps

from api.metrics import api_request_count

__all__ = ["api_operation"]

STATUS_CODE = "status_code"
PROCESSING_TIME = "processing_time"
logger = logging.getLogger(__name__)


def api_operation(old_func):
    """
    Marks an API request operation. This means:
    * API request counter is incremented on every call.
    * Log the api method name (on entry and exist) and http status code
    """

    @wraps(old_func)
    def new_func(*args, **kwargs):
        contextual_data = {}

        logger.debug("Entering %s", old_func.__name__)

        api_request_count.inc()

        start_time = time.perf_counter()
        results = old_func(*args, **kwargs)
        end_time = time.perf_counter()

        contextual_data[STATUS_CODE] = _get_status_code(results)

        contextual_data[PROCESSING_TIME] = end_time - start_time

        logger.debug("Leaving %s", old_func.__name__, extra=contextual_data)
        return results

    return new_func


def _get_status_code(results):
    if isinstance(results, str):
        # Flask interprets a string response as a HTTP 200
        return 200
    elif isinstance(results, int):
        return results
    elif isinstance(results, tuple):
        return results[1]

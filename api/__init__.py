import logging
import time

from flask import request
from functools import wraps

from api.metrics import api_request_count

__all__ = ["api_operation"]

REQUEST_ID_HEADER = "x-rh-insights-request-id"
UNKNOWN_REQUEST_ID_VALUE = "-1"
REQUEST_ID = "request_id"
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
        contextual_data = _create_contextual_data()

        logger.debug("Entering %s(args:%s, kwargs:%s)",
                     old_func.__name__, args, kwargs,
                     extra=contextual_data)

        api_request_count.inc()

        start_time = time.perf_counter()
        results = old_func(*args, **kwargs)
        end_time = time.perf_counter()

        _add_status_code_to_contextual_data(contextual_data, results)

        _add_processing_time_to_contextual_data(contextual_data,
                                                end_time - start_time)

        logger.debug("Leaving %s", old_func.__name__, extra=contextual_data)
        return results

    return new_func


def _create_contextual_data():
    return {REQUEST_ID: _get_request_id(request.headers)}


def _get_request_id(request_headers):
    request_id = request_headers.get(REQUEST_ID_HEADER,
                                     UNKNOWN_REQUEST_ID_VALUE)
    return request_id


def _add_status_code_to_contextual_data(contextual_data, results):
    if isinstance(results, str):
        contextual_data[STATUS_CODE] = 200
    elif isinstance(results, int):
        contextual_data[STATUS_CODE] = results
    elif isinstance(results, tuple):
        contextual_data[STATUS_CODE] = results[1]


def _add_processing_time_to_contextual_data(contextual_data, processing_time):
    contextual_data[PROCESSING_TIME] = processing_time

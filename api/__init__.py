import time
from functools import reduce
from functools import wraps
from http import HTTPStatus

import flask
import ujson
from ratelimit import RateLimitException

from api.metrics import api_request_count
from api.segmentio import segmentio_track
from app.logging import get_logger

__all__ = ["api_operation"]

STATUS_CODE = "status_code"
PROCESSING_TIME = "processing_time"

ESCAPE_CHARS = '.?+*|{}[]()"\\#@&<>~$'

logger = get_logger(__name__)


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

        try:
            segmentio_track(old_func.__name__, contextual_data[PROCESSING_TIME], contextual_data, logger)
        except RateLimitException:
            logger.debug("segmentio_track: rate limit exceeded.")

        logger.debug("Leaving %s", old_func.__name__, extra=contextual_data)
        return results

    return new_func


def _get_status_code(results):
    if isinstance(results, str):
        # Flask interprets a string response as a HTTP 200
        return HTTPStatus.OK
    elif isinstance(results, int):
        return results
    elif isinstance(results, tuple):
        return results[1]
    elif isinstance(results, flask.Response):
        return results.status_code
    else:
        return -1


def flask_json_response(json_data, status=HTTPStatus.OK):
    return flask.Response(ujson.dumps(json_data), status=status, mimetype="application/json")


def build_collection_response(data, page, per_page, total):
    return {"total": total, "count": len(data), "page": page, "per_page": per_page, "results": data}


def custom_escape(expression):
    return reduce(lambda x, y: x + "\\" + y if y in ESCAPE_CHARS else x + y, expression, "")


def json_error_response(title, detail, status=HTTPStatus.BAD_REQUEST):
    return flask_json_response({"title": title, "detail": detail}, status)


def pagination_params(page, per_page):
    limit = per_page
    offset = (page - 1) * per_page
    return limit, offset

from __future__ import annotations

import logging
import time
from collections.abc import Callable

_DEFAULT_ACCEPT_ERROR = Exception("no valid result obtained")

logger = logging.getLogger(__name__)


def accept_when[T](
    func: Callable[[], T],
    is_valid: Callable[[T], bool],
    delay: float | None = None,
    retries: int | None = None,
    error: Exception | None = _DEFAULT_ACCEPT_ERROR,
) -> T:
    """
    This function was created to address the delay issue that came with
    the usage of xjoin as a datasource.

    When HBI is set to use xjoin as a datasource there is a delay between creating a host
    and then to be able to search that host.


    :param func: callable that returns a result
    :param is_valid: function to validate the result
    :param delay: time before retrying the function, defaults to 0.5
    :param retries: number of retries, defaults to 10
    :return: result
    """
    if delay is None:
        delay = 0.5
    if retries is None:
        retries = 10
    response: T | None = None
    for retry_number in range(retries):
        if retry_number:
            logger.info("Retrying in %s second(s)...", delay)
            time.sleep(delay)

        logger.info("Attempt %s to fetch resource", retry_number)
        response = func()
        if is_valid(response):
            return response
    else:
        if error is None:
            assert response is not None
            return response
        raise error

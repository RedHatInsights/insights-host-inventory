# mypy: disallow-untyped-defs

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import pytest
from urllib3.connectionpool import HTTPConnectionPool

logger = logging.getLogger(__name__)

RATE_LIMITED_HOST_SUFFIX = "redhat.com"
READ_METHODS = frozenset({"GET", "HEAD"})

_throttling = threading.local()


def get_throttled_time() -> float:
    """Return the total time (in seconds) the current thread has spent waiting on rate limits."""
    return getattr(_throttling, "seconds", 0.0)


class RequestPacer:
    """Thread-safe limiter that spaces calls at least ``1 / rate`` seconds apart.

    Keeping a constant spacing between requests guarantees that both the burst and the
    average rate limits are respected, no matter how long the measuring window is.
    """

    def __init__(self, rate: float) -> None:
        self._interval = 1 / rate
        self._next_slot = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            slot = max(time.monotonic(), self._next_slot)
            self._next_slot = slot + self._interval
        delay = slot - time.monotonic()
        if delay > 0:
            time.sleep(delay)
            _throttling.seconds = get_throttled_time() + delay


@contextmanager
def rate_limit_http_requests(
    requests_per_second: float, write_requests_per_second: float
) -> Generator[None]:
    """Throttle all HTTP requests to the rate limited hosts made via urllib3 in this process.

    Patching urllib3 covers every client used by the tests (apigen clients, IQE's
    ``RobustSession``/``requests``, other plugins' bindings), including retries and redirects.
    Every request counts towards ``requests_per_second``, and non-read requests also count
    towards ``write_requests_per_second``. The limits apply per process, so they are not
    respected when running tests in parallel (e.g. with pytest-xdist).
    """
    all_requests_pacer = RequestPacer(requests_per_second)
    write_requests_pacer = RequestPacer(write_requests_per_second)
    original_urlopen = HTTPConnectionPool.urlopen

    def rate_limited_urlopen(
        pool: HTTPConnectionPool, method: str, url: str, *args: Any, **kwargs: Any
    ) -> Any:
        if pool.host and pool.host.endswith(RATE_LIMITED_HOST_SUFFIX):
            if method.upper() not in READ_METHODS:
                write_requests_pacer.wait()
            all_requests_pacer.wait()
        return original_urlopen(pool, method, url, *args, **kwargs)

    logger.info(
        "Rate limiting HTTP requests to *%s: %s req/s in total, %s req/s for non-GET/HEAD",
        RATE_LIMITED_HOST_SUFFIX,
        requests_per_second,
        write_requests_per_second,
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(HTTPConnectionPool, "urlopen", rate_limited_urlopen)
        yield

import os
import sys

from app.utils import HostWrapper

# Make test helpers available to be imported
sys.path.append(os.path.join(os.path.dirname(__file__), "helpers"))

# Make fixtures available
pytest_plugins = [
    "tests.fixtures.api_fixtures",
    "tests.fixtures.app_fixtures",
    "tests.fixtures.db_fixtures",
    "tests.fixtures.mq_fixtures",
    "tests.fixtures.tracker_fixtures",
]


def pytest_assertrepr_compare(config, op, left, right):
    """
    until pytest diffs multiline repr: https://github.com/pytest-dev/pytest/issues/8346
    """
    if isinstance(left, HostWrapper) and isinstance(right, HostWrapper) and op == "==":
        res = config.hook.pytest_assertrepr_compare(config=config, op=op, left=repr(left), right=repr(right))
        return res[0]


def pytest_sessionfinish():
    """Remove handlers from all loggers"""
    import logging

    loggers = [logging.getLogger()] + list(logging.Logger.manager.loggerDict.values())
    for logger in loggers:
        if not hasattr(logger, "handlers"):
            continue
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

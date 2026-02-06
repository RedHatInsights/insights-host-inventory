#!/usr/bin/python3
import sys
from functools import partial

from app.logging import get_logger
from app.logging import threadctx
from jobs.common import excepthook
from jobs.common import job_setup
from lib.db import session_guard
from lib.host_synchronize import sync_group_data

__all__ = ("main", "run")

PROMETHEUS_JOB = "inventory-host-group-synchronizer"
LOGGER_NAME = "inventory_host_group_synchronizer"


def run(config, logger, session, shutdown_handler):
    update_count, failed_count = sync_group_data(session, config.script_chunk_size, shutdown_handler.shut_down)
    logger.info(f"Total number of host.groups updated: {update_count}")
    logger.info(f"Total number of hosts failed to update: {failed_count}")


def main(logger):
    config, session, _, _, shutdown_handler, application = job_setup((), PROMETHEUS_JOB)

    with session_guard(session), application.app.app_context():
        run(config, logger, session, shutdown_handler)


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)
    job_type = "Host group synchronizer"
    sys.excepthook = partial(excepthook, logger, job_type)

    threadctx.request_id = None
    main(logger)

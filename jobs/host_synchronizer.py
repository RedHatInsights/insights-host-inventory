#!/usr/bin/python3
import sys
from functools import partial

from prometheus_client import CollectorRegistry
from prometheus_client import push_to_gateway

from app.logging import get_logger
from app.logging import threadctx
from app.models import Host
from app.models import Staleness
from app.queue.metrics import event_producer_failure
from app.queue.metrics import event_producer_success
from app.queue.metrics import event_serialization_time
from jobs.common import excepthook
from jobs.common import job_setup
from jobs.common import prometheus_job
from lib.db import session_guard
from lib.handlers import register_shutdown
from lib.host_synchronize import synchronize_hosts
from lib.metrics import synchronize_fail_count
from lib.metrics import synchronize_host_count

__all__ = ("main", "run")

PROMETHEUS_JOB = "inventory-synchronizer"
LOGGER_NAME = "inventory_synchronizer"
COLLECTED_METRICS = (
    synchronize_host_count,
    synchronize_fail_count,
    event_producer_failure,
    event_producer_success,
    event_serialization_time,
)


@synchronize_fail_count.count_exceptions()
def run(config, logger, session, event_producer, shutdown_handler):
    query_hosts = session.query(Host)
    query_staleness = session.query(Staleness)
    update_count = synchronize_hosts(
        query_hosts, query_staleness, event_producer, config.script_chunk_size, config, shutdown_handler.shut_down
    )
    logger.info(f"Total number of hosts synchronized: {update_count}")
    return update_count


def main(logger):
    config, session, event_producer, _, shutdown_handler, application = job_setup((), PROMETHEUS_JOB)

    # Register additional metrics not handled by job_setup
    registry = CollectorRegistry()
    for metric in COLLECTED_METRICS:
        registry.register(metric)

    job = prometheus_job(config.kubernetes_namespace, PROMETHEUS_JOB)
    prometheus_shutdown = partial(push_to_gateway, config.prometheus_pushgateway, job, registry)
    register_shutdown(prometheus_shutdown, "Pushing metrics")

    with session_guard(session), application.app.app_context():
        run(config, logger, session, event_producer, shutdown_handler)


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)
    job_type = "Host synchronizer"
    sys.excepthook = partial(excepthook, logger, job_type)

    threadctx.request_id = None
    main(logger)

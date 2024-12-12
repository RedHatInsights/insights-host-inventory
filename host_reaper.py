import sys
from functools import partial

from sqlalchemy import or_

from app.environment import RuntimeEnvironment
from app.logging import get_logger
from app.logging import threadctx
from app.models import Host
from app.queue.metrics import event_producer_failure
from app.queue.metrics import event_producer_success
from app.queue.metrics import event_serialization_time
from jobs.common import excepthook
from jobs.common import find_hosts_in_state
from jobs.common import main
from lib.host_delete import delete_hosts
from lib.metrics import delete_host_count
from lib.metrics import delete_host_processing_time
from lib.metrics import host_reaper_fail_count

__all__ = ("main", "run")

PROMETHEUS_JOB = "inventory-reaper"
LOGGER_NAME = "host_reaper"
COLLECTED_METRICS = (
    delete_host_count,
    delete_host_processing_time,
    host_reaper_fail_count,
    event_producer_failure,
    event_producer_success,
    event_serialization_time,
)
RUNTIME_ENVIRONMENT = RuntimeEnvironment.JOB


@host_reaper_fail_count.count_exceptions()
def run(config, logger, session, event_producer, notification_event_producer, shutdown_handler, application):
    with application.app.app_context():
        filter_hosts_to_delete = find_hosts_in_state(logger, session, ["culled"])

        query = session.query(Host).filter(or_(False, *filter_hosts_to_delete))
        hosts_processed = config.host_delete_chunk_size
        deletions_remaining = query.count()

        while hosts_processed == config.host_delete_chunk_size:
            logger.info(f"Reaper starting batch; {deletions_remaining} remaining.")
            try:
                events = delete_hosts(
                    query,
                    event_producer,
                    notification_event_producer,
                    config.host_delete_chunk_size,
                    shutdown_handler.shut_down,
                    control_rule="REAPER",
                )
                hosts_processed = len(list(events))
            except InterruptedError:
                events = []
                hosts_processed = 0

            deletions_remaining -= hosts_processed


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)
    job_type = "Host reaper"
    sys.excepthook = partial(excepthook, logger, job_type)

    threadctx.request_id = None
    config, logger, session, event_producer, notification_event_producer, shutdown_handler, application = main(
        logger, COLLECTED_METRICS, PROMETHEUS_JOB
    )
    run(config, logger, session, event_producer, notification_event_producer, shutdown_handler, application)

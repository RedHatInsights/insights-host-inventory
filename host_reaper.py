#!/usr/bin/python
import sys
from functools import partial

from sqlalchemy import ColumnElement
from sqlalchemy import and_
from sqlalchemy import or_

from app.environment import RuntimeEnvironment
from app.logging import get_logger
from app.logging import threadctx
from app.models import Host
from app.models import Staleness
from app.queue.metrics import event_producer_failure
from app.queue.metrics import event_producer_success
from app.queue.metrics import event_serialization_time
from jobs.common import excepthook
from jobs.common import job_setup as host_reaper_job_setup
from lib.host_delete import delete_hosts
from lib.host_repository import find_hosts_by_staleness_job
from lib.host_repository import find_hosts_sys_default_staleness
from lib.metrics import delete_host_count
from lib.metrics import delete_host_processing_time
from lib.metrics import host_reaper_fail_count

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


def filter_hosts_in_state_using_custom_staleness(logger, session, state: list):
    staleness_objects = session.query(Staleness).all()
    org_ids = []

    query_filters = []
    for staleness_obj in staleness_objects:
        # Validate which host types for a given org_id never get deleted
        logger.debug(f"Looking for hosts from org_id {staleness_obj.org_id} that use custom staleness")
        org_ids.append(staleness_obj.org_id)
        query_filters.append(
            and_(
                (Host.org_id == staleness_obj.org_id),
                find_hosts_by_staleness_job(state, staleness_obj.org_id),
            )
        )
    return query_filters, org_ids


def filter_hosts_in_state_using_sys_default_staleness(logger, org_ids, state: list) -> ColumnElement:
    # Use the hosts_ids_list to exclude hosts that were found with custom staleness
    logger.debug("Looking for hosts that use system default staleness")
    return and_(~Host.org_id.in_(org_ids), find_hosts_sys_default_staleness(state))


def find_hosts_in_state(logger, session, state: list):
    # Find all host ids that are using custom staleness
    query_filters, org_ids = filter_hosts_in_state_using_custom_staleness(logger, session, state)

    # Find all host ids that are not using custom staleness,
    # excluding the hosts for the org_ids that use custom staleness
    query_filters.append(filter_hosts_in_state_using_sys_default_staleness(logger, org_ids, state))

    return query_filters


@host_reaper_fail_count.count_exceptions()
def run(config, logger, session, event_producer, notification_event_producer, shutdown_handler, application):
    with application.app.app_context():
        filter_hosts_to_delete = find_hosts_in_state(logger, session, ["culled"])

        # Adhoc fix for RHINENG-16901
        # hosts reporter by rhsm-system-profile-bridge are not being deleted
        # when marked as culled, and are also prevented to stay culled as w
        # we are forcing its modified_on and last_check_in to be updated.

        rhsm_bridge_hosts_query = session.query(Host).filter(
            and_(or_(False, *filter_hosts_to_delete), Host.reporter == "rhsm-system-profile-bridge")
        )

        for host in rhsm_bridge_hosts_query.yield_per(config.host_delete_chunk_size):
            host._update_modified_date()
            host._update_last_check_in_date()

        query = session.query(Host).filter(
            and_(or_(False, *filter_hosts_to_delete), Host.reporter != "rhsm-system-profile-bridge")
        )
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
    config, session, event_producer, notification_event_producer, shutdown_handler, application = (
        host_reaper_job_setup(COLLECTED_METRICS, PROMETHEUS_JOB)
    )
    run(config, logger, session, event_producer, notification_event_producer, shutdown_handler, application)

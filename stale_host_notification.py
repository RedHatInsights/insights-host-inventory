#!/usr/bin/python
import sys
from functools import partial

from sqlalchemy import or_

from app.auth.identity import create_mock_identity_with_org_id
from app.auth.identity import to_auth_header
from app.instrumentation import log_host_stale_notification_succeeded
from app.logging import get_logger
from app.logging import threadctx
from app.models import Host
from app.queue.host_mq import OperationResult
from app.queue.notifications import NotificationType
from app.queue.notifications import send_notification
from jobs.common import excepthook
from jobs.common import find_hosts_in_state
from jobs.common import main

LOGGER_NAME = "stale_host_notification"
PROMETHEUS_JOB = "inventory-stale-host-notification"
COLLECTED_METRICS = (
    # add metric
)


def _create_host_operation_result(host, identity, logger):
    return OperationResult(
        host,
        {"b64_identity": to_auth_header(identity)} if identity else None,
        None,
        None,
        None,
        partial(log_host_stale_notification_succeeded, logger, host.id, control_rule="HOST_STALE_NOTIFICATION"),
    )


def run(config, logger, session, event_producer, notification_event_producer, shutdown_handler, application):
    with application.app.app_context():
        filter_stale_hosts = find_hosts_in_state(logger, session, ["stale_in"], config)

        query = session.query(Host).filter(or_(False, *filter_stale_hosts))
        stale_hosts = query.all()
        if len(stale_hosts) > 0:
            logger.info("%s hosts found as stale")
            for host in stale_hosts:
                identity = create_mock_identity_with_org_id(host.org_id)
                result = _create_host_operation_result(host, identity, logger)
                send_notification(
                    notification_event_producer, NotificationType.system_became_stale, vars(result.host_row)
                )
        else:
            logger.info("No hosts found as stale")


if __name__ == "__main__":
    logger = get_logger(LOGGER_NAME)
    job_type = "Stale host notification"
    sys.excepthook = partial(excepthook, logger, job_type)

    threadctx.request_id = None
    config, logger, session, event_producer, notification_event_producer, shutdown_handler, application = main(
        logger, COLLECTED_METRICS, PROMETHEUS_JOB
    )
    run(config, logger, session, event_producer, notification_event_producer, shutdown_handler, application)

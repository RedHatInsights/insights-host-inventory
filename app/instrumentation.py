from flask import g

from app.queue.metrics import event_producer_failure
from app.queue.metrics import event_producer_success
from app.queue.metrics import rbac_access_denied
from app.queue.metrics import rbac_fetching_failure


def message_produced(logger, value, key, headers, record_metadata):
    status = "PRODUCED"
    offset = record_metadata.offset
    timestamp = record_metadata.timestamp
    topic = record_metadata.topic
    extra = {"status": status, "offset": offset, "timestamp": timestamp, "topic": topic, "key": key}

    info_extra = {**extra, "headers": headers}
    info_message = "Message %s offset=%d timestamp=%d topic=%s, key=%s, headers=%s"
    logger.info(info_message, status, offset, timestamp, topic, key, headers, extra=info_extra)

    debug_message = "Message offset=%d timestamp=%d topic=%s key=%s value=%s"
    debug_extra = {**extra, "value": value}
    logger.debug(debug_message, offset, timestamp, topic, key, value, extra=debug_extra)

    event_producer_success.labels(event_type=headers["event_type"], topic=topic).inc()


def message_not_produced(logger, topic, value, key, headers, error):
    status = "NOT PRODUCED"
    error_message = str(error)
    extra = {"status": status, "topic": topic, "key": key}

    info_extra = {**extra, "headers": headers, "error": error_message}
    info_message = "Message %s topic=%s, key=%s, headers=%s, error=%s"
    logger.error(info_message, status, topic, key, headers, error, extra=info_extra)

    debug_message = "Message topic=%s key=%s value=%s"
    debug_extra = {**extra, "value": value}
    logger.debug(debug_message, topic, key, value, extra=debug_extra)

    event_producer_failure.labels(event_type=headers["event_type"], topic=topic).inc()


def _control_rule():
    if hasattr(g, "access_control_rule"):
        return g.access_control_rule
    else:
        return "None"


def log_host_deleted(logger, host_id):
    logger.info("Deleted host: %s", host_id, extra={"Access Control Rule Invoked": _control_rule()})


def log_host_not_deleted(logger, host_id):
    logger.info(
        "Hostidentity %s already deleted. Delete event not emitted.",
        host_id,
        extra={"Access Control Rule Invoked": _control_rule()},
    )


def log_host_list_get_succeded(logger, results_list):
    logger.debug("Found hosts: %s", results_list, extra={"Access Control Rule Invoked": _control_rule()})
    logger.debug("rule used REMOVE: %s", _control_rule())


def rbac_failure(logger, error_message=None):
    logger.error("Failed to fetch RBAC permissions: %s", error_message)
    rbac_fetching_failure.inc()


def rbac_permission_denied(logger, required_permission, user_permissions):
    logger.debug(
        "Access denied due to RBAC",
        extra={"required_permission": required_permission, "user_permissions": user_permissions},
    )
    rbac_access_denied.labels(required_permission=required_permission).inc()

from functools import partial

from confluent_kafka import KafkaException

from app.auth.identity import to_auth_header
from app.instrumentation import log_host_delete_succeeded
from app.logging import get_logger
from app.models import Host
from app.models import HostGroupAssoc
from app.models import deleted_by_this_query
from app.queue.event_producer import EventProducer
from app.queue.events import EventType
from app.queue.host_mq import OperationResult
from app.queue.host_mq import write_delete_event_message
from app.queue.notifications import NotificationType
from app.queue.notifications import send_notification
from lib.db import session_guard
from lib.host_kafka import kafka_available
from lib.metrics import delete_host_count
from lib.metrics import delete_host_processing_time
from utils.system_profile_log import extract_host_model_sp_to_log

__all__ = ("delete_hosts",)
logger = get_logger(__name__)


def _delete_host_db_records(select_query, chunk_size, identity, interrupt, control_rule) -> list[OperationResult]:
    results_list = []

    for host in select_query.limit(chunk_size):
        with delete_host_processing_time.time():
            result = _delete_host(select_query.session, host, identity, control_rule)
        if deleted_by_this_query(result.host_row):
            results_list.append(result)

        if interrupt():
            raise InterruptedError()

    return results_list


def _send_delete_messages_for_batch(
    processed_rows: list[OperationResult],
    event_producer: EventProducer,
    notification_event_producer: EventProducer,
    initiated_by_frontend: bool,
):
    for result in processed_rows:
        if result is not None:
            delete_host_count.inc()
            write_delete_event_message(event_producer, result, initiated_by_frontend)
            send_notification(notification_event_producer, NotificationType.system_deleted, vars(result.host_row))


def delete_hosts(
    select_query,
    event_producer,
    notification_event_producer,
    chunk_size,
    interrupt=lambda: False,
    identity=None,
    control_rule=None,
    initiated_by_frontend=False,
):
    while select_query.count():
        if kafka_available():
            with session_guard(select_query.session):
                batch_events = _delete_host_db_records(select_query, chunk_size, identity, interrupt, control_rule)
                _send_delete_messages_for_batch(
                    batch_events, event_producer, notification_event_producer, initiated_by_frontend
                )

                # yield the items in batch_events
                yield from batch_events

        else:
            logger.error("Host batch not deleted because Kafka server not available.")
            raise KafkaException("Kafka server not available. Stopping host deletions.")


def _delete_host(session, host, identity, control_rule) -> OperationResult:
    sp_fields_to_log = extract_host_model_sp_to_log(host)
    assoc_delete_query = session.query(HostGroupAssoc).filter(HostGroupAssoc.host_id == host.id)
    host_delete_query = session.query(Host).filter(Host.id == host.id)
    assoc_delete_query.delete(synchronize_session="fetch")
    host_delete_query.delete(synchronize_session="fetch")
    return OperationResult(
        host,
        {"b64_identity": to_auth_header(identity)} if identity else None,
        None,
        None,
        EventType.delete,
        partial(log_host_delete_succeeded, logger, host.id, control_rule, sp_fields_to_log),
    )

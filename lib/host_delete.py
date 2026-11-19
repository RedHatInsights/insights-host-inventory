from __future__ import annotations

from collections.abc import Callable
from collections.abc import Generator
from functools import partial

from confluent_kafka import KafkaException
from flask_sqlalchemy.query import Query
from sqlalchemy.orm import Session

from app.audit import AuditEvent
from app.audit import capture_audit_context
from app.auth.identity import Identity
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


def _delete_host_db_records(
    select_query: Query,
    chunk_size: int,
    identity: Identity | None,
    interrupt: Callable[[], bool],
    control_rule: str | None,
    audit_events: list[AuditEvent],
) -> list[OperationResult]:
    results_list = []

    # Caller queries may group/join for RBAC, so lock only the outer host rows.
    # SEC-MON-REQ-1 EOI-1/3: a competing delete must not become our audited success.
    candidates = select_query.with_entities(Host.id, Host.org_id).limit(chunk_size).subquery()
    locked_hosts = (
        select_query.session.query(Host)
        .join(candidates, (Host.id == candidates.c.id) & (Host.org_id == candidates.c.org_id))
        .with_for_update(of=Host)
        .populate_existing()
    )
    for host in locked_hosts:
        event = _delete_audit_event(host, identity, control_rule)
        audit_events.append(event)
        with delete_host_processing_time.time():
            result = _delete_host(select_query.session, host, identity, control_rule)
        if deleted_by_this_query(result.row):
            result.audit_events.append(event)
            results_list.append(result)

        if interrupt():
            raise InterruptedError()

    return results_list


def _send_delete_messages_for_batch(
    processed_rows: list[OperationResult],
    event_producer: EventProducer,
    notification_event_producer: EventProducer,
    initiated_by_frontend: bool,
) -> None:
    for result in processed_rows:
        if result is not None:
            delete_host_count.inc()
            write_delete_event_message(event_producer, result, initiated_by_frontend, log_success=False)
            send_notification(notification_event_producer, NotificationType.system_deleted, vars(result.row))


def delete_hosts(
    select_query: Query,
    event_producer: EventProducer,
    notification_event_producer: EventProducer,
    chunk_size: int,
    interrupt: Callable[[], bool] = lambda: False,
    identity: Identity | None = None,
    control_rule: str | None = None,
    initiated_by_frontend: bool = False,
) -> Generator[OperationResult]:
    """This function will yield nothing if no hosts are found."""
    while select_query.count():
        if kafka_available():
            audit_events: list[AuditEvent] = []
            try:
                with session_guard(select_query.session):
                    batch_events = _delete_host_db_records(
                        select_query, chunk_size, identity, interrupt, control_rule, audit_events
                    )
                    _send_delete_messages_for_batch(
                        batch_events, event_producer, notification_event_producer, initiated_by_frontend
                    )
            except Exception as exc:
                # SEC-MON-REQ-1 EOI-1/11: failed publication/commit rolls this batch back.
                for event in audit_events:
                    event.emit(
                        "failure", reason="interrupted" if isinstance(exc, InterruptedError) else "delete_failed"
                    )
                raise

            # SEC-MON-REQ-1 EOI-1: neither audit nor operational success precedes commit.
            for result in batch_events:
                for event in result.audit_events:
                    event.emit("success")
                result.success_logger()
            yield from batch_events

        else:
            logger.error("Host batch not deleted because Kafka server not available.")
            for host in select_query.limit(chunk_size):
                _delete_audit_event(host, identity, control_rule).emit("failure", reason="publication_unavailable")
            raise KafkaException("Kafka server not available. Stopping host deletions.")


def _delete_audit_event(host: Host, identity: Identity | None, control_rule: str | None) -> AuditEvent:
    context = (
        capture_audit_context(identity)
        if identity is not None
        else capture_audit_context(
            system_actor=f"host-delete:{control_rule}" if control_rule else "host-delete", org_id=host.org_id
        )
    )
    return AuditEvent("DELETE", "host", str(host.id), context)


def _delete_host(session: Session, host: Host, identity: Identity | None, control_rule: str | None) -> OperationResult:
    sp_fields_to_log = extract_host_model_sp_to_log(host)
    org_id = identity.org_id if identity else host.org_id
    assoc_delete_query = session.query(HostGroupAssoc).filter(
        HostGroupAssoc.org_id == org_id, HostGroupAssoc.host_id == host.id
    )
    assoc_delete_query.delete(synchronize_session="fetch")

    # Use ORM delete instead of bulk delete so SQLAlchemy events fire
    # This allows automatic outbox entry creation via event listener
    # See lib/host_outbox_events.py
    session.delete(host)
    session.flush()

    return OperationResult(
        host,
        {"b64_identity": to_auth_header(identity)} if identity else None,
        None,
        EventType.delete,
        partial(log_host_delete_succeeded, logger, host.id, control_rule, sp_fields_to_log),
    )

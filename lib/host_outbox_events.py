"""
Automatic outbox event creation for Host model changes.

This module provides SQLAlchemy event listeners that automatically create
outbox entries when hosts are created, updated, or deleted. Outbox entries
are created when:
- A host is created
- A host is deleted
- A host is updated and one of these fields changes:
  - satellite_id
  - subscription_manager_id
  - insights_id
  - ansible_host
  - groups (group_id)
"""

from sqlalchemy import event
from sqlalchemy import inspect
from sqlalchemy.orm import Session
from sqlalchemy.orm import object_session

from app.exceptions import OutboxSaveException
from app.logging import get_logger
from app.models import Host
from app.queue.events import EventType
from lib import outbox_repository

logger = get_logger(__name__)

# Fields that trigger outbox entries when changed
OUTBOX_TRIGGER_FIELDS = {
    "satellite_id",
    "subscription_manager_id",
    "insights_id",
    "ansible_host",
    "groups",
}

# Track pending outbox operations per session using a dictionary keyed by session ID
# Flask-SQLAlchemy's scoped session proxy doesn't reliably preserve attributes
# We use weak references conceptually by only storing host_id strings, not Host objects
_pending_outbox_ops = {}


def _get_pending_ops(session):
    """Get or create pending outbox operations list for a session."""
    session_id = id(session)
    if session_id not in _pending_outbox_ops:
        _pending_outbox_ops[session_id] = []
    return _pending_outbox_ops[session_id]


def _has_outbox_relevant_changes(host: Host, log_level="debug") -> bool:
    """
    Check if any outbox-relevant fields have changed.

    Returns True if any of the tracked fields (satellite_id, subscription_manager_id,
    insights_id, ansible_host, or groups) have been modified.

    Note: This function should be called when change history is available (after_update or before_flush).
    """
    inspected = inspect(host)
    for field_name in OUTBOX_TRIGGER_FIELDS:
        if field_name in inspected.attrs:
            history = inspected.attrs[field_name].history
            if history.has_changes():
                log_msg = f"Field {field_name} changed for host {host.id}"
                if log_level == "info":
                    logger.info(log_msg)
                else:
                    logger.debug(log_msg)
                return True
    return False


def _track_operation(session, event_type: str, host_id: str):
    """Helper to track an outbox operation, avoiding duplicates."""
    ops = _get_pending_ops(session)
    # Check if already tracked
    if not any(op[0] == event_type and op[1] == host_id for op in ops):
        ops.append((event_type, host_id))
        logger.debug(f"Tracked {event_type} for host {host_id}")
        return True
    return False


@event.listens_for(Host, "after_insert", propagate=True)
def _track_host_created(mapper, connection, host: Host):  # noqa: ARG001
    """Track that a host was created - will write outbox entry before commit."""
    session = object_session(host) or Session(bind=connection)
    _track_operation(session, "created", str(host.id))


@event.listens_for(Host, "after_update", propagate=True)
def _track_host_updated(mapper, connection, host: Host):  # noqa: ARG001
    """Track host updates when relevant fields change."""
    if _has_outbox_relevant_changes(host):
        session = object_session(host) or Session(bind=connection)
        _track_operation(session, "updated", str(host.id))


@event.listens_for(Session, "before_flush", propagate=True)
def _check_host_changes_before_flush(session, flush_context, instances):  # noqa: ARG001
    """
    Fallback: check for host changes before flush.
    Ensures we capture changes even if after_update didn't fire.
    """
    for instance in session.dirty:
        if isinstance(instance, Host) and _has_outbox_relevant_changes(instance, log_level="info"):
            _track_operation(session, "updated", str(instance.id))


@event.listens_for(Host, "before_delete", propagate=True)
def _track_host_deleted(mapper, connection, host: Host):  # noqa: ARG001
    """Track that a host was deleted - will write outbox entry before commit."""
    session = object_session(host) or Session(bind=connection)
    _track_operation(session, "delete", str(host.id))


def _process_outbox_ops_list(session, ops):
    """Process a list of pending outbox operations."""
    for event_type_str, host_id in ops:
        try:
            event_type = EventType[event_type_str] if event_type_str != "delete" else EventType.delete

            # For delete events, host is None which is expected
            # For create/update events, reload the host from the database
            # We don't store host objects to avoid keeping session references
            host = None
            if event_type != EventType.delete:
                try:
                    # Always reload from database to ensure we have a fresh object
                    # attached to the current session
                    host = session.query(Host).filter(Host.id == host_id).first()
                    if host is None:
                        # Host was deleted, skip this outbox entry
                        logger.debug(f"Host {host_id} was deleted, skipping outbox entry for {event_type_str}")
                        continue
                    logger.debug(f"Reloaded host {host_id} from database for outbox entry")

                except Exception as e:
                    # If we can't reload the host, skip this entry
                    logger.error(f"Could not reload host {host_id} for outbox entry: {str(e)}, skipping")
                    continue

            logger.info(f"Processing outbox entry for {event_type_str} event: host {host_id}")
            result = outbox_repository.write_event_to_outbox(event_type, host_id, host, session=session)
            if not result:
                raise OutboxSaveException(f"Failed to write {event_type_str} host event to outbox")
            logger.info(f"Successfully created outbox entry for {event_type_str}: {host_id}")
        except OutboxSaveException:
            logger.error(f"Failed to write {event_type_str} event to outbox for host {host_id}")
            raise
        except Exception as e:
            error_str = str(e).lower()
            if "already flushing" in error_str:
                logger.warning(f"Skipping outbox op for {host_id} - session is flushing")
                continue
            logger.error(f"Unexpected error creating outbox entry for {event_type_str}: {str(e)}")
            raise OutboxSaveException(f"Unexpected error creating outbox entry: {str(e)}") from e


def _collect_all_pending_ops():
    """Collect all pending ops from all sessions and return (ops_list, session_ids_set)."""
    ops_to_process = []
    processed_session_ids = set()
    for sid, ops in list(_pending_outbox_ops.items()):
        if ops:
            ops_to_process.extend(ops)
            processed_session_ids.add(sid)
    return ops_to_process, processed_session_ids


@event.listens_for(Session, "before_commit", propagate=True)
def _process_pending_outbox_ops_before_commit(session):  # noqa: ARG001
    """
    Process pending outbox operations before commit.
    Note: With Flask-SQLAlchemy, before_commit may fire before commit's internal flush,
    so some ops may be added after this runs and will be cleared in after_commit.
    """
    session_id = id(session)
    logger.debug(f"before_commit for session {session_id}")

    ops_to_process, processed_session_ids = _collect_all_pending_ops()

    if ops_to_process:
        logger.info(f"Processing {len(ops_to_process)} pending outbox operations")
        try:
            _process_outbox_ops_list(session, ops_to_process)
            for sid in processed_session_ids:
                _pending_outbox_ops.pop(sid, None)
            session._outbox_ops_processed = True
        except Exception as e:
            logger.error(f"Error processing outbox ops: {e}", exc_info=True)


@event.listens_for(Session, "after_flush", propagate=True)
def _verify_pending_outbox_ops_after_flush(session, flush_context):  # noqa: ARG001
    """
    Verify pending outbox operations after flush completes.
    Processing happens in before_commit to avoid "Session is already flushing" errors.
    """
    session_id = id(session)
    if session_id in _pending_outbox_ops:
        ops = _pending_outbox_ops[session_id]
        logger.debug(f"Verified {len(ops)} pending outbox operations after flush for session {session_id}")


@event.listens_for(Session, "after_commit", propagate=True)
def _clear_pending_outbox_ops_after_commit(session):  # noqa: ARG001
    """Clear pending outbox operations after commit."""
    session_id = id(session)

    # Clear the processed flag
    if hasattr(session, "_outbox_ops_processed"):
        delattr(session, "_outbox_ops_processed")

    # Check for unprocessed ops (added during commit's flush, after before_commit)
    ops_to_clear, session_ids = _collect_all_pending_ops()
    if ops_to_clear:
        logger.warning(
            f"Found {len(ops_to_clear)} unprocessed outbox ops after commit - "
            "these were added during commit's flush after before_commit fired"
        )
        for sid in session_ids:
            _pending_outbox_ops.pop(sid, None)

    # Clear remaining ops for this session
    _pending_outbox_ops.pop(session_id, None)


@event.listens_for(Session, "after_rollback", propagate=True)
def _clear_pending_outbox_ops_after_rollback(session):  # noqa: ARG001
    """Clear pending outbox operations after rollback to prevent memory leaks."""
    session_id = id(session)
    _pending_outbox_ops.pop(session_id, None)

    # Safety net: if dict grows very large, clear all entries
    if len(_pending_outbox_ops) > 1000:
        logger.warning(f"Clearing {len(_pending_outbox_ops)} pending outbox ops to prevent resource leak")
        _pending_outbox_ops.clear()

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

from typing import Any

from sqlalchemy import event
from sqlalchemy import inspect
from sqlalchemy.ext.mutable import MutableList
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


def _get_pending_ops(session):
    """Get or create pending outbox operations list for a session."""
    if "pending_ops" not in session.info:
        session.info["pending_ops"] = []
    return session.info["pending_ops"]


def _extract_group_ids(groups_list: list[Any] | tuple[Any, ...] | MutableList | None) -> set[str]:
    """
    Extract group IDs from a groups list, handling various SQLAlchemy history formats.

    SQLAlchemy history can return groups in different formats:
    - An empty list: []
    - A tuple containing the list: ([...],)
    - A list containing the list: [[...]]
    - Just the list: [...]
    - A list of MutableList objects: [MutableList([dict]), MutableList([dict]), ...] (for multiple groups)
      Each MutableList typically contains a single dict, but can contain multiple

    Args:
        groups_list: The groups list from SQLAlchemy history (deleted/added)

    Returns:
        A set of group ID strings extracted from the groups list
    """
    if not groups_list:
        return set()

    # Handle wrapper cases: tuple/list containing a single list
    if isinstance(groups_list, (tuple, list)) and len(groups_list) == 1:
        inner = groups_list[0]
        if isinstance(inner, (list, tuple, MutableList)):
            # Unwrap: ([...],) or [[...]] -> [...]
            groups_list = inner

    # Ensure we have an iterable list
    if not isinstance(groups_list, (list, tuple, MutableList)):
        # If it's a single item, wrap it in a list
        groups_list = [groups_list] if groups_list else []

    # Extract group IDs, handling both dicts and MutableList objects
    group_ids = set()
    for item in groups_list:
        if isinstance(item, dict):
            # Direct dict: extract ID
            if "id" in item:
                group_ids.add(str(item["id"]))
        elif isinstance(item, MutableList):
            # MutableList wrapper: iterate through it to find dicts
            for sub_item in item:
                if isinstance(sub_item, dict) and "id" in sub_item:
                    group_ids.add(str(sub_item["id"]))
        elif isinstance(item, (list, tuple)):
            # Nested list/tuple: recursively extract
            group_ids.update(_extract_group_ids(item))

    return group_ids


def _has_outbox_relevant_changes(host: Host) -> bool:
    """
    Check if any outbox-relevant fields have changed.

    Returns True if any of the tracked fields (satellite_id, subscription_manager_id,
    insights_id, ansible_host, or group IDs) have been modified.

    Note: For groups field, only group ID changes trigger outbox events, not group name changes,
    since the outbox payload only includes workspace_id (group ID), not the group name.

    Note: This function should be called when change history is available (after_update or before_flush).
    """
    inspected = inspect(host)
    for field_name in OUTBOX_TRIGGER_FIELDS:
        if field_name in inspected.attrs:
            history = inspected.attrs[field_name].history
            if history.has_changes():
                # Special handling for groups field: only trigger if group IDs changed
                if field_name == "groups":
                    # For MutableList, history.deleted contains the old value and history.added contains the new value
                    # Extract group IDs from old and new values
                    old_group_ids = _extract_group_ids(history.deleted) if history.deleted else set()
                    new_group_ids = (
                        _extract_group_ids(history.added)
                        if history.added
                        else _extract_group_ids(getattr(host, "groups", []))
                    )

                    # Only trigger if group IDs changed (not just names)
                    if old_group_ids != new_group_ids:
                        logger.debug(f"Group IDs changed for host {host.id}: {old_group_ids} -> {new_group_ids}")
                        return True
                    else:
                        logger.debug(
                            f"Groups field changed for host {host.id} \
                                but group IDs unchanged (likely name change only)"
                        )
                        continue

                logger.debug(f"Field {field_name} changed for host {host.id}")
                return True
    return False


def _get_session_for_instance(instance, connection):
    """Get session for an instance, with fallback to creating one from connection."""
    return object_session(instance) or Session(bind=connection)


def _track_operation(session, event_type: str, host_id: str):
    """Helper to track an outbox operation, avoiding duplicates."""
    ops = _get_pending_ops(session)
    # Check if already tracked
    if not any(op[0] == event_type and op[1] == host_id for op in ops):
        ops.append((event_type, host_id))
        logger.debug(f"Tracked {event_type} for host {host_id}")
        return True
    return False


# Event handler callback: registered with SQLAlchemy, not called directly
@event.listens_for(Host, "after_insert", propagate=True)
def _track_host_created(mapper, connection, host: Host):  # noqa: ARG001
    """Track that a host was created - will write outbox entry before commit."""
    session = _get_session_for_instance(host, connection)
    _track_operation(session, "created", str(host.id))


# Event handler callback: registered with SQLAlchemy, not called directly
@event.listens_for(Host, "after_update", propagate=True)
def _track_host_updated(mapper, connection, host: Host):  # noqa: ARG001
    """Track host updates when relevant fields change."""
    if _has_outbox_relevant_changes(host):
        session = _get_session_for_instance(host, connection)
        _track_operation(session, "updated", str(host.id))


# Event handler callback: registered with SQLAlchemy, not called directly
@event.listens_for(Session, "before_flush", propagate=True)
def _check_host_changes_before_flush(session, flush_context, instances):  # noqa: ARG001
    """
    Fallback: check for host changes before flush.
    Ensures we capture changes even if after_update didn't fire.
    """
    for instance in session.dirty:
        if isinstance(instance, Host) and _has_outbox_relevant_changes(instance):
            _track_operation(session, "updated", str(instance.id))


# Event handler callback: registered with SQLAlchemy, not called directly
@event.listens_for(Host, "before_delete", propagate=True)
def _track_host_deleted(mapper, connection, host: Host):  # noqa: ARG001
    """Track that a host was deleted - will write outbox entry before commit."""
    session = _get_session_for_instance(host, connection)
    _track_operation(session, "delete", str(host.id))


def _process_outbox_ops_list(session, ops):
    """Process a list of pending outbox operations."""
    for event_type_str, host_id in ops:
        try:
            event_type = EventType[event_type_str]

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

            logger.debug(f"Processing outbox entry for {event_type_str} event: host {host_id}")
            result = outbox_repository.write_event_to_outbox(event_type, host_id, host, session=session)
            if not result:
                raise OutboxSaveException(f"Failed to write {event_type_str} host event to outbox")
            logger.debug(f"Successfully created outbox entry for {event_type_str}: {host_id}")
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


def _collect_pending_ops_for_session(session):
    """
    Collect pending ops for the CURRENT session only.

    This ensures that we only process outbox entries for hosts that were
    modified in the same session that's about to commit, preventing session
    mismatch issues where Session A tries to write outbox entries for hosts
    created/updated in Session B.
    """
    return session.info.get("pending_ops", [])


# Event handler callback: registered with SQLAlchemy, not called directly
@event.listens_for(Session, "before_commit", propagate=True)
def _process_pending_outbox_ops_before_commit(session):
    """
    Process pending outbox operations before commit.

    CRITICAL: Only processes operations for the CURRENT session to ensure
    that outbox writes and host/group writes happen in the same transaction.

    This prevents:
    - Session A writing outbox entries for hosts created in Session B
    - Orphan outbox entries if Session B rolls back
    - Missing outbox entries if Session A rolls back
    """
    ops_to_process = _collect_pending_ops_for_session(session)

    if ops_to_process:
        logger.debug(f"before_commit for session with {len(ops_to_process)} pending ops")
        logger.debug(f"Processing {len(ops_to_process)} pending outbox operations for current session")
        try:
            _process_outbox_ops_list(session, ops_to_process)
            # Clear the current session's ops after processing
            session.info.pop("pending_ops", None)
        except Exception as e:
            logger.error(f"Error processing outbox ops in before_commit: {e}", exc_info=True)
            # Re-raise to ensure transaction rollback
            raise


# Event handler callback: registered with SQLAlchemy, not called directly
@event.listens_for(Session, "after_commit", propagate=True)
def _clear_pending_outbox_ops_after_commit(session):
    """Clear pending outbox operations after commit."""
    # Check for any remaining unprocessed ops for THIS session only
    # (added during commit's flush, after before_commit)
    # Note: We CANNOT process these here because the session is in 'committed' state
    # and no further SQL can be emitted. These operations were tracked too late.
    if ops_remaining := session.info.get("pending_ops", []):
        logger.warning(
            f"Found {len(ops_remaining)} outbox ops for session that were tracked during commit's flush. "
            "These operations were tracked too late to be processed. "
            "This typically happens when hosts are modified without an explicit flush before commit."
        )

    # Clear remaining ops for this session
    session.info.pop("pending_ops", None)


# Event handler callback: registered with SQLAlchemy, not called directly
@event.listens_for(Session, "after_rollback", propagate=True)
def _clear_pending_outbox_ops_after_rollback(session):  # noqa: ARG001
    """Clear pending outbox operations after rollback to prevent memory leaks."""
    # Data is automatically cleaned up when session is garbage collected
    session.info.pop("pending_ops", None)

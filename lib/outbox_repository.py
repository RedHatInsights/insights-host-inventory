import json
import uuid

from marshmallow import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.exceptions import OutboxSaveException
from app.logging import get_logger
from app.models.database import db
from app.models.host import Host
from app.models.outbox import Outbox
from app.models.schemas import OutboxSchema
from app.queue.events import EventType
from lib.metrics import outbox_save_failure
from lib.metrics import outbox_save_success

logger = get_logger(__name__)


def need_outbox_entry(
    host_id: str,
    satellite_id: str | None,
    subscription_manager_id: str | None,
    insights_id: str | None,
    ansible_host: str | None,
    group_id: str | None,
) -> bool:
    """
    Check if an outbox entry is needed by comparing input parameters with the host's current values in the database.

    Args:
        host_id: The ID of the host to check
        satellite_id: The satellite ID to compare
        subscription_manager_id: The subscription manager ID to compare
        insights_id: The insights ID to compare
        ansible_host: The ansible host to compare
        group_id: The group ID to compare (will be compared against groups[0].id)

    Returns:
        True if any of the parameters differ from the host's current values in the database
    """
    # Query the database directly to get the host's current values
    # Use a fresh session to avoid any in-memory state
    from sqlalchemy.orm import sessionmaker

    from app.models.database import db as db_engine

    # Create a fresh session to get the original database values
    fresh_session = sessionmaker(bind=db_engine.engine)()
    try:
        host = fresh_session.query(Host).filter(Host.id == host_id).first()
    except Exception as e:
        # If we can't query the host (e.g., invalid UUID), assume we need an outbox entry
        logger.debug(f"Error querying host {host_id}: {e}. Assuming outbox entry is needed.")
        fresh_session.close()
        return True
    finally:
        fresh_session.close()

    if not host:
        logger.info(f"Host with id {host_id} not found in database, should be created and outbox entry needed")
        return True

    # Define field comparisons as tuples of (input_value, db_value, field_name)
    field_comparisons = [
        (satellite_id, host.satellite_id, "satellite_id"),
        (subscription_manager_id, host.subscription_manager_id, "subscription_manager_id"),
        (insights_id, host.insights_id, "insights_id"),
        (ansible_host, host.ansible_host, "ansible_host"),
    ]

    # Check all simple field comparisons
    for input_value, db_value, field_name in field_comparisons:
        if input_value != db_value:
            logger.debug(f"{field_name} differs: input={input_value}, db={db_value}")
            return True

    # Handle group_id comparison separately due to its special logic
    current_group_id = None
    if host.groups and len(host.groups) > 0:
        # groups is a list of serialized group objects, get the id from the first group
        current_group_id = host.groups[0].get("id") if isinstance(host.groups[0], dict) else str(host.groups[0].id)

    if group_id != current_group_id:
        logger.debug(f"group_id differs: input={group_id}, db={current_group_id}")
        return True

    logger.debug(f"All outbox parameters match for host {host_id}, no outbox entry needed")
    return False


def remove_event_from_outbox(key):
    try:
        db.session.query(Outbox).filter(Outbox.aggregateid == key).delete()
        db.session.commit()
    except OutboxSaveException as ose:
        logger.error(f"Error removing event from outbox: {ose}")
        raise OutboxSaveException(f"Error removing event from outbox: {ose}") from ose


def _create_update_event_payload(host: Host) -> dict:
    if not host or not host.id:
        logger.error("Missing required field 'id' in host data")
        raise OutboxSaveException("Missing required field 'id' in host data")

    metadata = {
        "local_resource_id": str(host.id),
        "api_href": "https://apihref.com/",
        "console_href": "https://www.console.com/",
        "reporter_version": "1.0",
        "transaction_id": str(uuid.uuid4()),
    }

    groups = host.groups
    common = {"workspace_id": groups[0]["id"]} if len(groups) > 0 else {}

    reporter = {
        "satellite_id": str(host.satellite_id) if host.satellite_id else None,
        "subscription_manager_id": str(host.subscription_manager_id) if host.subscription_manager_id else None,
        "insights_id": str(host.insights_id) if host.insights_id else None,
        "ansible_host": str(host.ansible_host) if host.ansible_host else None,
    }

    representations = {
        "metadata": metadata,
        "common": common,
        "reporter": reporter,
    }

    return {
        "type": "host",
        "reporter_type": "hbi",
        "reporter_instance_id": "redhat",
        "representations": representations,
    }


def _delete_event_payload(host_id: str) -> dict:
    if not host_id:
        logger.error("Missing required field 'host_id' from the 'delete' event")
        raise OutboxSaveException("Missing required field 'host_id' from the 'delete' event")

    reporter = {"type": "HBI"}
    reference = {"resource_type": "host", "resource_id": host_id, "reporter": reporter}

    return {"reference": reference}


def _report_error(message: str) -> None:
    outbox_save_failure.inc()
    logger.error(message)
    raise OutboxSaveException(message)


def _build_outbox_entry(event: EventType, host_id: str, host: Host | None = None) -> dict:
    try:
        if event in {EventType.created, EventType.updated} and not host:
            _report_error("Missing required 'host data' for 'created' or 'updated' event for Outbox")

        op = "ReportResource" if event in {EventType.created, EventType.updated} else "DeleteResource"
        outbox_entry: dict[str, str | dict] = {
            "aggregateid": str(host_id),
            "aggregatetype": "hbi.hosts",
            "operation": op,
            "version": "v1beta2",
        }

        if event in {EventType.created, EventType.updated}:
            try:
                # host is guaranteed to be non-None due to check on line 77-78
                assert host is not None
                payload = _create_update_event_payload(host)
                outbox_entry["payload"] = payload
            except OutboxSaveException as ose:
                _report_error(f"Failed to create payload for 'created' or 'updated' event for Outbox: {str(ose)}")
        else:
            try:
                payload = _delete_event_payload(str(host_id))
                outbox_entry["payload"] = payload
            except OutboxSaveException as ose:
                _report_error(f"Failed to create payload for 'delete' event for Outbox: {str(ose)}")
    except KeyError as e:
        _report_error(f"Missing required field in event data: {str(e)}. Event: {event}")

    except json.JSONDecodeError as e:
        _report_error(f"Failed to parse event JSON: {str(e)}. Event: {event}")

    except Exception as e:
        _report_error(f"Unexpected error writing event to outbox: {str(e)}")

    return outbox_entry


def write_event_to_outbox(
    event: EventType, host_id: str, host: Host | None = None, session: Session | None = None
) -> bool:
    """
    Check if outbox entry is needed, then build and write the outbox entry if necessary.
    """
    if not event:
        _report_error(f"Missing required field 'event': {event}")

    if not host_id:
        _report_error(f"Missing required field 'host_id': {host_id}")

    if not session:
        session = db.session

    # Check if outbox entry is needed before proceeding
    if host is not None:
        # For API updates, check if the host has been modified in the current session
        # This is more reliable than comparing with database values
        if hasattr(host, "_sa_instance_state") and db.session.is_modified(host):
            logger.debug("Host %s has been modified in current session, outbox entry needed", host_id)
        else:
            # For direct calls (like in tests) or MQ updates, always create outbox entries
            # since they represent explicit requests to create events
            logger.debug("Direct call to write_event_to_outbox for host %s, creating outbox entry", host_id)

    try:
        outbox_entry = _build_outbox_entry(event, host_id, host)
        validated_outbox_entry = OutboxSchema().load(outbox_entry)
    except ValidationError as ve:
        raise OutboxSaveException("Invalid host or event was provided") from ve

    logger.debug(
        f"Creating outbox entry: aggregateid={validated_outbox_entry['aggregateid']}, \
            type={validated_outbox_entry['operation']}"
    )
    # Write to outbox table in same transaction - let caller handle commit/rollback
    try:
        outbox_entry_db = Outbox(
            aggregateid=validated_outbox_entry["aggregateid"],
            aggregatetype=validated_outbox_entry["aggregatetype"],
            operation=validated_outbox_entry["operation"],
            version=validated_outbox_entry["version"],
            payload=validated_outbox_entry["payload"],
        )

        logger.debug("Adding the event to outbox:")
        logger.debug(validated_outbox_entry)

        # Save the outbox entry to record the event in the write-ahead log.
        session.add(outbox_entry_db)

        # Adding flush for emitting the event to outbox
        session.flush()
        session.delete(outbox_entry_db)

        outbox_save_success.inc()
        logger.debug("Added outbox entry to session: aggregateid=%s", validated_outbox_entry["aggregateid"])
        logger.debug("Successfully added event to outbox for aggregateid=%s", validated_outbox_entry["aggregateid"])

        return True

    except SQLAlchemyError as db_error:
        # Log error but don't handle rollback - let caller handle transaction
        logger.error("Database error while adding to outbox: %s", str(db_error))
        outbox_save_failure.inc()

        # Check if it's a table doesn't exist error
        error_str = str(db_error).lower()
        if "table" in error_str and ("does not exist" in error_str or "doesn't exist" in error_str):
            logger.error("Outbox table does not exist. Run database migrations first.")
            logger.error("Try: flask db upgrade")

        import traceback

        logger.debug("Database error traceback: %s", traceback.format_exc())

        # Re-raise the exception so caller can handle rollback
        raise OutboxSaveException("Failed to save event to outbox") from db_error

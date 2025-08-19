import json
from marshmallow import ValidationError
from sqlalchemy.exc import SQLAlchemyError

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


def _create_update_event_payload(host: Host) -> dict:

    if not host or not host.id:
        logger.error("Missing required field 'id' in host data")
        raise OutboxSaveException("Missing required field 'id' in host data")

    metadata = {
        "localResourceId": str(host.id),
        "apiHref": "https://apiHref.com/",
        "consoleHref": "https://www.console.com/",
        "reporterVersion": "1.0",
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
        "reporterType": "hbi",
        "reporterInstanceId": "redhat.com",
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


def _build_outbox_entry(event: EventType, host_id: str, host: Host or None = None) -> dict:
    try:
        if event not in {EventType.created, EventType.updated, EventType.delete}:
            _report_error(f"Invalid event type: {event}")

        if event in {EventType.created, EventType.updated} and not host:
            _report_error("Missing required 'host data' for 'created' or 'updated' event for Outbox")

        op = "ReportResource" if event in {EventType.created, EventType.updated} else "DeleteResource"
        outbox_entry = {
            "aggregateid": str(host_id),
            "aggregatetype": "hbi.hosts",
            "operation": op,
            "version": "v1beta2",
        }

        if event in {EventType.created, EventType.updated}:
            payload = _create_update_event_payload(host)
            if payload is None:
                _report_error("Failed to create payload for 'created' or 'updated' event for Outbox")
            outbox_entry["payload"] = payload
        elif event == EventType.delete:
            payload = _delete_event_payload(str(host_id))
            if payload is None:
                _report_error("Failed to create payload for 'delete' event")
            outbox_entry["payload"] = payload
        else:
            _report_error("Unknown event type.  Valid event types are 'created', 'updated', or 'delete'")
    except KeyError as e:
        _report_error(f"Missing required field in event data: {str(e)}. Event: {event}")

    except json.JSONDecodeError as e:
        _report_error(f"Failed to parse event JSON: {str(e)}. Event: {event}")

    except Exception as e:
        _report_error(f"Unexpected error writing event to outbox: {str(e)}")

    return outbox_entry


def write_event_to_outbox(event: EventType, host_id: str, host: Host or None = None) -> bool:
    """
    First check if required fields are present then build the outbox entry.
    """
    if not event:
        _report_error(f"Missing required field 'event': {event}")

    if not host_id:
        _report_error(f"Missing required field 'host_id': {host_id}")

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

        # Save the outbox entry to record the event in the write-ahead log.
        db.session.add(outbox_entry_db)
        db.session.flush()

        # This commit is required because session.add() and session.flush() do not commit the transaction
        db.session.commit()

        outbox_save_success.inc()
        logger.debug("Added outbox entry to session: aggregateid=%s", validated_outbox_entry["aggregateid"])
        logger.info("Successfully added event to outbox for aggregateid=%s", validated_outbox_entry["aggregateid"])

        # prune the new event from the Outbox table
        # Without the previous commit, the following delete will fail because the outbox entry is not yet committed.
        db.session.query(Outbox).filter(Outbox.aggregateid == validated_outbox_entry["aggregateid"]).delete()
        db.session.commit()

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

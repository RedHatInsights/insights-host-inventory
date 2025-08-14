import json
from typing import Literal
from typing import Union
from uuid import UUID

from app.exceptions import OutboxSaveException
from app.models.host import Host
from marshmallow import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.logging import get_logger
from app.models.database import db
from app.models.outbox import Outbox
from app.models.schemas import OutboxSchema
from lib.metrics import outbox_save_failure
from lib.metrics import outbox_save_success

logger = get_logger(__name__)


def _create_update_event_payload(host: Host) -> dict:
    if not host:
        logger.error("Missing required field 'host' in event data")

        raise OutboxSaveException("Missing required field 'host' in event data")

    if not host.id:
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
        "satellite_id": host.satellite_id,
        "subscription_manager_id": host.subscription_manager_id,
        "insights_id": host.insights_id,
        "ansible_host": host.ansible_host,
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


def _create_outbox_entry(event: str, host_id: str, host: Host or None = None) -> Union[dict, None, Literal[False]]:
    try:
        if event not in {"created", "updated", "delete"}:
            logger.error("Invalid event type: %s", event)
            return False

        if event in {"created", "updated"} and not host:
            logger.error("Missing required 'host data' for 'created/updated' event")
            return False

        op = "ReportResource" if event in {"created", "updated"} else "DeleteResource"
        outbox_entry = {
            "aggregateid": str(host_id),
            "aggregatetype": "hbi.hosts",
            "operation": op ,
            "version": "v1beta2"
        }

        if event in {"created", "updated"}:
            payload = _create_update_event_payload(host)
            if payload is None:
                logger.error("Failed to create payload for created/updated event")
                return False
            outbox_entry["payload"] = payload
        elif event == "delete":
            payload = _delete_event_payload(str(host_id))
            if payload is None:
                logger.error("Failed to create payload for delete event")
                return False
            outbox_entry["payload"] = payload
        else:
            logger.error('Unknown event type.  Valid event types are "created", "updated", or "delete"')
            return False
    except KeyError as e:
        logger.error("Missing required field in event data: %s. Event: %s", str(e), event)
        return False

    except json.JSONDecodeError as e:
        logger.error("Failed to parse event JSON: %s. Event: %s", str(e), event)
        return False

    except Exception as e:
        logger.error("Unexpected error writing event to outbox: %s. Event: %s", str(e), event)
        import traceback

        logger.error("Traceback: %s", traceback.format_exc())
        return False
    return outbox_entry


def write_event_to_outbox(event: str, host_id: str, host: Host or None = None) -> bool:
    # TODO: Add a test for this function
    # TODO: Check comments in this 
    """
    Add an event to the outbox table within the current database transaction.

    This function adds the outbox entry to the current database session but does not
    commit the transaction. The caller is responsible for committing or rolling back
    the transaction. If an error occurs, OutboxSaveException is raised to allow
    the caller to handle rollback.

    Args:
        event: Event data as JSON string containing type and host information

    Returns:
        bool: True if successfully added to session

    Raises:
        OutboxSaveException: If there's an error adding to the outbox
    """
    if not event:
        logger.error("Missing required field 'event'")
        return False

    if not host_id:
        logger.error("Missing required field 'event'")
        return False

    # if not host:
    #     logger.error("Missing required field 'host'")
    #     return False

    try:
        outbox_entry = _create_outbox_entry(event, host_id, host)
        if outbox_entry is None:
            # Notification event skipped - this is success
            logger.debug("Event skipped for outbox processing")
            return True
        if outbox_entry is False:
            logger.error("Failed to create outbox entry from event data")
            return False
        validated_outbox_entry = OutboxSchema().load(outbox_entry)
    except ValidationError as ve:
        from app.exceptions import OutboxSaveException

        logger.exception(
            f'Input validation error, "{str(ve.messages)}", \
                while creating outbox_entry: {outbox_entry if "outbox_entry" in locals() else "N/A"}'
        )
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

        db.session.add(outbox_entry_db)
        # Do not flush or commit - let the caller handle transaction lifecycle
        outbox_save_success.inc()
        logger.debug("Added outbox entry to session: aggregateid=%s", validated_outbox_entry["aggregateid"])

        logger.info("Successfully added event to outbox for aggregateid=%s", validated_outbox_entry["aggregateid"])
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
        from app.exceptions import OutboxSaveException

        raise OutboxSaveException("Failed to save event to outbox") from db_error

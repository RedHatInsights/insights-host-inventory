import json
from typing import Literal
from typing import Union

from marshmallow import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.exceptions import OutboxSaveException
from app.logging import get_logger
from app.models.database import db
from app.models.outbox import Outbox
from app.models.schemas import OutboxSchema
from lib.metrics import outbox_save_failure
from lib.metrics import outbox_save_success

logger = get_logger(__name__)


def _create_update_event_payload(host) -> Union[dict, None]:
    if not host:
        logger.error("Missing required field 'host' in event data")

        # TODO: raise an error
        return None

    # Handle both nested structure (test format) and flat structure (production format)
    if "id" in host:
        host_id = host["id"]
    else:
        logger.error("Missing required field 'id' in host data")
        return None

    metadata = {
        "localResourceId": host_id,
        "apiHref": "https://apiHref.com/",
        "consoleHref": "https://www.console.com/",
        "reporterVersion": "1.0",
    }

    groups = host.get("groups", [])
    common = {"workspace_id": groups[0]["id"]} if len(groups) > 0 else {}

    reporter = {
        "satellite_id": host.get("satellite_id", None),
        "subscription_manager_id": host.get("subscription_manager_id", None),
        "insights_id": host.get("insights_id", None),
        "ansible_host": host.get("ansible_host", None),
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


def _delete_event_payload(host) -> Union[dict, None]:
    if not host:
        logger.error("Missing required field 'host' in event data")

        # TODO: raise exception with ValueError based on checking
        return None

    # Handle both nested structure (test format) and flat structure (production format)
    if "id" in host:
        host_id = host["id"]
    else:
        logger.error("Missing required field 'id' in host data")
        return None

    reporter = {"type": "HBI"}
    reference = {"resource_type": "host", "resource_id": host_id, "reporter": reporter}

    return {"reference": reference}

    # staleness_obj = serialize_staleness_to_dict(get_staleness_obj(identity.org_id))
    # validated_data = StalenessSchema().load({**staleness_obj, **body})


def _create_outbox_entry(event: str) -> Union[dict, None, Literal[False]]:
    try:
        event_dict = json.loads(event) if isinstance(event, str) else event

        # Validate required fields
        if "type" in event_dict:
            event_type = event_dict["type"]
        elif "event_type" in event_dict:
            # This is a notification event, not a host event - skip outbox processing
            logger.debug("Skipping notification event for outbox: %s", event_dict.get("event_type"))
            return None  # Return None to indicate successful skip (not an error)
        else:
            logger.error("Missing required field 'type' in event data")
            return False

        # Handle both nested structure (test format) and flat structure (production format)
        if "host" in event_dict:
            # Test format: {"type": "...", "host": {"id": "...", ...}}
            host = event_dict["host"]
            if "id" not in host:
                logger.error("Missing required field 'host.id' in event data")
                return False
            host_id = host["id"]
        elif "id" in event_dict:
            # Production format: {"type": "...", "id": "...", ...}
            host_id = event_dict["id"]
            host = event_dict  # Use the whole event as host data for flat structure
        else:
            logger.error("Missing required field 'id' in event data")
            return False

        outbox_entry = {
            "aggregate_id": host_id,
            "aggregate_type": "hbi.hosts",
            "event_type": event_type,
        }

        if event_type in {"created", "updated"}:
            payload = _create_update_event_payload(host)
            if payload is None:
                logger.error("Failed to create payload for created/updated event")
                return False
            outbox_entry["payload"] = payload
        elif event_type == "delete":
            payload = _delete_event_payload(host)
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


def write_event_to_outbox(event: str) -> bool:
    """
    Write an event to the outbox table.

    Args:
        event: Event data as JSON string containing type and host information

    Returns:
        bool: True if successfully written to database, False if failed
    """
    if not event:
        logger.error("Missing required field 'event'")
        return False

    try:
        outbox_entry = _create_outbox_entry(event)
        if outbox_entry is None:
            # Notification event skipped - this is success
            logger.debug("Event skipped for outbox processing")
            return True
        elif outbox_entry is False:
            logger.error("Failed to create outbox entry from event data")
            return False
        validated_outbox_entry = OutboxSchema().load(outbox_entry)
    except ValidationError as ve:
        logger.exception(
            f'Input validation error, "{str(ve.messages)}", \
                while creating outbox_entry: {outbox_entry if "outbox_entry" in locals() else "N/A"}'
        )
        raise OutboxSaveException("Invalid host or event was provided") from ve

    logger.debug(
        f"Creating outbox entry: aggregate_id={validated_outbox_entry['aggregate_id']}, \
            type={validated_outbox_entry['event_type']}"
    )

    # Write to outbox table in same transaction without using session_guard to avoid DetachedInstanceError
    try:
        outbox_entry_db = Outbox(
            aggregate_id=validated_outbox_entry["aggregate_id"],
            aggregate_type=validated_outbox_entry["aggregate_type"],
            event_type=validated_outbox_entry["event_type"],
            payload=validated_outbox_entry["payload"],
        )
        db.session.add(outbox_entry_db)
        db.session.flush()  # Ensure it's written before commit
        outbox_save_success.inc()
        logger.debug("Successfully wrote event to outbox: outbox_id=%s", outbox_entry_db.id)

        logger.info("Successfully wrote event to outbox for aggregate_id=%s", validated_outbox_entry["aggregate_id"])
        return True

    except SQLAlchemyError as db_error:
        return _extracted_from_write_event_to_outbox(db_error)


# TODO Rename this here and in `write_event_to_outbox`
def _extracted_from_write_event_to_outbox(db_error):
    logger.error("Database error while writing to outbox: %s", str(db_error))
    outbox_save_failure.inc()

    # Check if it's a table doesn't exist error
    error_str = str(db_error).lower()
    if "table" in error_str and ("does not exist" in error_str or "doesn't exist" in error_str):
        logger.error("Outbox table does not exist. Run database migrations first.")
        logger.error("Try: flask db upgrade")

    import traceback

    logger.debug("Database error traceback: %s", traceback.format_exc())
    return False

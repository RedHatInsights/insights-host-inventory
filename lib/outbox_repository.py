import json

# Try to import Flask dependencies, fallback to basic logging if not available
# TODO: Remove these conditional imports
try:
    from app.logging import get_logger
    from app.models.database import db
    from app.models.outbox import Outbox
    from lib.db import session_guard
    from lib.metrics import outbox_save_failure
    from lib.metrics import outbox_save_success

    logger = get_logger(__name__)
    FLASK_AVAILABLE = True
except ImportError as e:
    import logging

    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(__name__)
    logger.warning(f"Flask dependencies not available: {e}")
    FLASK_AVAILABLE = False

from sqlalchemy import JSON
from sqlalchemy.exc import SQLAlchemyError


def _create_update_event_payload(event_dict) -> JSON:
    host = event_dict.get("host", {})
    if not host:
        logger.error("Missing required field 'host' in event data")

        # TODO: raise an error
        return None

    metadata = {
        "localResourceId": host["id"],
        "apiHref": "https://apiHref.com/",
        "consoleHref": "https://www.console.com/",
        "reporterVersion": "1.0",
    }

    groups = event_dict.get("host", {"groups": []}).get("groups")
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


def _delete_event_payload(event_dict) -> JSON:
    host = event_dict.get("host", {})
    if not host:
        logger.error("Missing required field 'host' in event data")

        # TODO: raise exception
        return None

    reporter = {"type": "HBI"}
    reference = {"resource_type": "host", "resource_id": host["id"], "reporter": reporter}

    return {"reference": reference}


def write_event_to_outbox(event: str) -> bool:
    """
    Write an event to the outbox table.

    Args:
        event: Event data as JSON string

    Returns:
        bool: True if successfully written to database, False if failed
    """
    try:
        # Convert event to dictionary from string
        event_dict = json.loads(event) if isinstance(event, str) else event
        logger.debug(
            "Writing event to outbox: type=%s, aggregate_id=%s",
            event_dict.get("type"),
            event_dict.get("host", {}).get("id"),
        )

        # Validate required fields
        if "type" not in event_dict:
            logger.error("Missing required field 'type' in event data")
            return False

        if "host" not in event_dict:
            logger.error("Missing required field 'host' in event data")
            return False

        if "id" not in event_dict["host"]:
            logger.error("Missing required field 'host.id' in event data")
            return False

        # Extract fields
        aggregate_id = event_dict["host"]["id"]
        event_type = event_dict["type"]
        payload = None
        if event_type in ["created", "updated"]:
            payload = _create_update_event_payload(event_dict)
        elif event_type == "delete":
            payload = _delete_event_payload(event_dict)
        else:
            logger.error('Unknown event type.  Valid event types are "created", "updated", or "delete"')
            return False

        if not payload:
            logger.error("Failed to create payload for event: %s", event)
            return False

        logger.debug("Creating outbox entry: aggregate_id=%s, type=%s", aggregate_id, event_type)

        # Write to outbox table within transaction
        try:
            with session_guard(db.session):
                outbox_entry = Outbox(
                    aggregate_id=aggregate_id,
                    aggregate_type="hbi.hosts",
                    event_type=event_type,
                    payload=json.dumps(payload),
                )
                db.session.add(outbox_entry)
                db.session.flush()  # Ensure it's written before commit
                outbox_save_success.inc()
                logger.debug("Successfully wrote event to outbox: outbox_id=%s", outbox_entry.id)

            logger.info("Successfully wrote event to outbox for aggregate_id=%s", aggregate_id)
            return True

        except SQLAlchemyError as db_error:
            logger.error("Database error while writing to outbox: %s", str(db_error))
            logger.error("Event data: %s", event)
            outbox_save_failure.inc()

            # Check if it's a table doesn't exist error
            error_str = str(db_error).lower()
            if "table" in error_str and ("does not exist" in error_str or "doesn't exist" in error_str):
                logger.error("Outbox table does not exist. Run database migrations first.")
                logger.error("Try: flask db upgrade")

            import traceback

            logger.debug("Database error traceback: %s", traceback.format_exc())
            return False

    except json.JSONDecodeError as e:
        logger.error("Failed to parse event JSON: %s. Event: %s", str(e), event)
        return False

    except Exception as e:
        logger.error("Unexpected error writing event to outbox: %s. Event: %s", str(e), event)
        import traceback

        logger.error("Traceback: %s", traceback.format_exc())
        return False

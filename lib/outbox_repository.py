import json

# from typing import Union, Dict, Any

# Try to import Flask dependencies, fallback to basic logging if not available
try:
    from app.logging import get_logger
    from app.models.database import db
    from app.models.outbox import Outbox
    from lib.db import session_guard

    logger = get_logger(__name__)
    FLASK_AVAILABLE = True
except ImportError as e:
    import logging

    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(__name__)
    logger.warning(f"Flask dependencies not available: {e}")
    FLASK_AVAILABLE = False


def _create_update_event_payload(event_dict):
    host = event_dict.get("host", {})
    if not host:
        logger.error("Missing required field 'host' in event data")
        return None

    metadata = {
        "localResourceId": host["id"],
        "apiHref": "https://apiHref.com/",
        "consoleHref": "https://www.console.com/",
        "reporterVersion": "1.0",
    }

    common = {"workpsace_id": event_dict["host"]["groups"][0]["id"]}

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


def _delete_event_payload(event_dict):
    host = event_dict.get("host", {})
    if not host:
        logger.error("Missing required field 'host' in event data")
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
    if not FLASK_AVAILABLE:
        logger.error("Flask dependencies not available - cannot write to outbox")
        return False

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
        if event_type in ["created", "updated"]:
            payload = _create_update_event_payload(event_dict)
        elif event_type == "delete":
            payload = _delete_event_payload(event_dict)
        else:
            logger.error('Unknown event type.  Valid event types are "created", "updated", or "delete"')
            return False

        logger.debug("Creating outbox entry: aggregate_id=%s, type=%s", aggregate_id, event_type)

        # Ensure database tables exist
        try:
            db.create_all()
            logger.debug("Database tables verified/created")
        except Exception as table_error:
            logger.warning("Could not create database tables: %s", table_error)
            # Continue anyway - tables might already exist

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
                logger.debug("Successfully wrote event to outbox: outbox_id=%s", outbox_entry.id)

            logger.info("Successfully wrote event to outbox for aggregate_id=%s", aggregate_id)
            return True

        except Exception as db_error:
            logger.error("Database error while writing to outbox: %s", str(db_error))
            logger.error("Event data: %s", event)

            # Check if it's a table doesn't exist error
            error_str = str(db_error).lower()
            if "table" in error_str and ("does not exist" in error_str or "doesn't exist" in error_str):
                logger.error("Outbox table does not exist. Run database migrations first.")
                logger.error("Try: flask db upgrade")

            import traceback

            logger.debug("Database error traceback: %s", traceback.format_exc())
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

import json
from typing import Union, Dict, Any

from app.logging import get_logger
from app.models.database import db
from app.models.outbox import Outbox
from lib.db import session_guard

logger = get_logger(__name__)


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
        logger.debug("Writing event to outbox: type=%s, aggregate_id=%s", 
                    event_dict.get("type"), event_dict.get("host", {}).get("id"))

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
        payload = event_dict.get("payload", event_dict["host"])
        
        logger.debug("Creating outbox entry: aggregate_id=%s, type=%s", aggregate_id, event_type)

        # Write to outbox table within transaction
        try:
            with session_guard(db.session):
                outbox_entry = Outbox(
                    aggregate_id=aggregate_id,
                    aggregate_type="hbi.hosts",
                    type=event_type,
                    payload=payload,
                )
                db.session.add(outbox_entry)
                db.session.flush()  # Ensure it's written before commit
                logger.debug("Successfully wrote event to outbox: outbox_id=%s", outbox_entry.id)

            logger.info("Successfully wrote event to outbox for aggregate_id=%s", aggregate_id)
            return True
            
        except Exception as db_error:
            logger.error("Database error while writing to outbox: %s", str(db_error))
            logger.error("Event data: %s", event)
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
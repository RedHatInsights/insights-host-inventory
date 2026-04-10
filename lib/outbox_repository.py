import json
import uuid

from marshmallow import ValidationError
from sqlalchemy import delete
from sqlalchemy import insert
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


# remove the processed host from the outbox table
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
    First check if required fields are present then build the outbox entry.
    """
    if not event:
        _report_error(f"Missing required field 'event': {event}")

    if not host_id:
        _report_error(f"Missing required field 'host_id': {host_id}")

    if not session:
        session = db.session

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


def write_events_to_outbox_batch(
    ops: list[tuple[EventType, str, "Host | None"]],
    session: Session,
) -> int:
    """
    Batch-write multiple outbox entries in a single transaction.

    Uses SQLAlchemy Core insert()/delete() to produce exactly 2 SQL statements
    (one multi-row INSERT, one bulk DELETE) regardless of the number of entries,
    instead of N+2 statements from the ORM add_all/flush path.

    The number of entries per call is naturally controlled by
    MQ_DB_BATCH_MAX_MESSAGES, which limits how many Kafka messages are
    consumed per transaction.

    Returns the count of successfully written entries.
    Raises OutboxSaveException if any entry fails to build or validate.
    """
    if not ops:
        return 0

    schema = OutboxSchema()
    values_dicts: list[dict] = []
    generated_ids: list[uuid.UUID] = []

    for event, host_id, host in ops:
        if not event:
            _report_error(f"Missing required field 'event': {event}")
        if not host_id:
            _report_error(f"Missing required field 'host_id': {host_id}")

        try:
            outbox_entry = _build_outbox_entry(event, host_id, host)
            validated = schema.load(outbox_entry)
        except ValidationError as ve:
            raise OutboxSaveException("Invalid host or event was provided") from ve

        row_id = uuid.uuid4()
        generated_ids.append(row_id)
        values_dicts.append(
            {
                "id": row_id,
                "aggregateid": validated["aggregateid"],
                "aggregatetype": validated["aggregatetype"],
                "operation": validated["operation"],
                "version": validated["version"],
                "payload": validated["payload"],
            }
        )

    try:
        session.execute(insert(Outbox), values_dicts)
        session.flush()
    except SQLAlchemyError as db_error:
        logger.error("Database error during batch outbox INSERT: %s", str(db_error))
        outbox_save_failure.inc()
        raise OutboxSaveException("Failed to batch-insert outbox entries") from db_error

    try:
        session.execute(delete(Outbox).where(Outbox.id.in_(generated_ids)))
    except SQLAlchemyError as db_error:
        logger.error("Database error during batch outbox DELETE: %s", str(db_error))
        outbox_save_failure.inc()
        raise OutboxSaveException("Failed to batch-delete outbox entries") from db_error

    count = len(values_dicts)
    outbox_save_success.inc(count)
    logger.debug("Batch-wrote %d outbox entries", count)
    return count

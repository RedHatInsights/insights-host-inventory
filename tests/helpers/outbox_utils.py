import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

from sqlalchemy import event

from app.models.outbox import Outbox


@contextmanager
def capture_outbox_calls(target: str, *, capture_groups: bool = False) -> Generator[list[dict[str, Any]], None, None]:
    """
    Context manager to capture calls to outbox write functions.

    Captures both single-entry (write_event_to_outbox) and batch
    (write_events_to_outbox_batch) calls by patching at the same module path.

    Args:
        target: fully-qualified patch target where write_event_to_outbox is imported
        (e.g. "lib.outbox_repository.write_event_to_outbox").
        capture_groups: if True and host_obj is provided, also capture host_obj.groups on each call.

    Yields:
        A list that will be appended with dictionaries describing each captured call.
    """

    calls: list[dict[str, Any]] = []

    def single_side_effect(event_type, host_id, host_obj=None, session=None):  # noqa: ARG001
        entry: dict[str, Any] = {
            "event_type": event_type,
            "host_id": host_id,
            "host": host_obj,
        }
        if capture_groups and host_obj is not None:
            entry["groups"] = host_obj.groups
        calls.append(entry)
        return True

    def batch_side_effect(ops, session):  # noqa: ARG001
        for event_type, host_id, host_obj in ops:
            entry: dict[str, Any] = {
                "event_type": event_type,
                "host_id": host_id,
                "host": host_obj,
            }
            if capture_groups and host_obj is not None:
                entry["groups"] = host_obj.groups
            calls.append(entry)
        return len(ops)

    # Derive the batch target from the single target
    assert "write_event_to_outbox" in target, f"target must reference 'write_event_to_outbox', got: {target}"
    batch_target = target.replace("write_event_to_outbox", "write_events_to_outbox_batch")

    with patch(target, side_effect=single_side_effect), patch(batch_target, side_effect=batch_side_effect):
        yield calls


def wait_for_all_events(
    event_producer: Any, expected_count: int, max_wait: float = 5.0, wait_interval: float = 0.1
) -> None:
    """Wait for event_producer.write_event to be called the expected number of times.

    This helper function polls the event_producer.write_event.call_count until it
    reaches the expected count or the maximum wait time is exceeded. This is useful
    for waiting for async operations to complete in tests.

    Args:
        event_producer: Mock event producer with write_event.call_count attribute
        expected_count: Expected number of times write_event should be called
        max_wait: Maximum wait time in seconds (default: 5.0)
        wait_interval: Time to wait between checks in seconds (default: 0.1)

    Raises:
        AssertionError: If the expected count is not reached within max_wait time
    """
    elapsed = 0.0
    while event_producer.write_event.call_count < expected_count and elapsed < max_wait:
        time.sleep(wait_interval)
        elapsed += wait_interval

    # Assert that we got the expected number of calls
    assert event_producer.write_event.call_count >= expected_count, (
        f"Expected {expected_count} events, but only got {event_producer.write_event.call_count} after {elapsed:.2f}s"
    )


@contextmanager
def assert_query_count(session, expected: int) -> Generator[list[str], None, None]:
    """Assert that exactly `expected` SQL statements are emitted within the block.

    Hooks into SQLAlchemy's before_cursor_execute event to record every statement.
    The captured list of SQL strings is yielded for further inspection.
    """
    queries: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        queries.append(statement)

    engine = session.get_bind()
    event.listen(engine, "before_cursor_execute", _record)
    try:
        yield queries
    finally:
        event.remove(engine, "before_cursor_execute", _record)

    assert len(queries) == expected, f"Expected {expected} queries, got {len(queries)}:\n" + "\n".join(
        f"  [{i}] {q[:200]}" for i, q in enumerate(queries)
    )


def assert_outbox_empty(db, host_id: str) -> None:
    count = db.session.query(Outbox).filter_by(aggregateid=host_id).count()
    assert count == 0


def build_updated_payload() -> dict[str, Any]:
    import uuid

    return {
        "aggregatetype": "hbi.hosts",
        "aggregateid": str(uuid.uuid4()),
        "operation": "updated",
        "version": "v1beta2",
        "payload": {
            "type": "host",
            "reporter_type": "hbi",
            "reporter_instance_id": "redhat.com",
            "representations": {
                "metadata": {
                    "local_resource_id": str(uuid.uuid4()),
                    "api_href": "https://apihref.com/",
                    "console_href": "https://www.console.com/",
                    "reporter_version": "1.0",
                    "transaction_id": str(uuid.uuid4()),
                },
                "common": {"workspace_id": str(uuid.uuid4())},
                "reporter": {
                    "satellite_id": None,
                    "subscription_manager_id": str(uuid.uuid4()),
                    "insights_id": str(uuid.uuid4()),
                    "ansible_host": None,
                },
            },
        },
    }


def build_delete_payload() -> dict[str, Any]:
    import uuid

    return {
        "aggregatetype": "hbi.hosts",
        "aggregateid": str(uuid.uuid4()),
        "operation": "DeleteResource",
        "version": "v1beta2",
        "payload": {
            "reference": {
                "resource_type": "host",
                "resource_id": str(uuid.uuid4()),
                "reporter": {"type": "HBI"},
            }
        },
    }

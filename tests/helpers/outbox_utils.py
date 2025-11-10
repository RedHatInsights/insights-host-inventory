import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

from app.models.outbox import Outbox


@contextmanager
def capture_outbox_calls(target: str, *, capture_groups: bool = False) -> Generator[list[dict[str, Any]], None, None]:
    """
    Context manager to capture calls to write_event_to_outbox.

    Args:
        target: fully-qualified patch target where write_event_to_outbox is imported
        (e.g. "api.host.write_event_to_outbox").
        capture_groups: if True and host_obj is provided, also capture host_obj.groups on each call.

    Yields:
        A list that will be appended with dictionaries describing each captured call.
    """

    calls: list[dict[str, Any]] = []

    def side_effect(event_type, host_id, host_obj=None, session=None):  # noqa: ARG001
        entry: dict[str, Any] = {
            "event_type": event_type,
            "host_id": host_id,
            "host": host_obj,
        }
        if capture_groups and host_obj is not None:
            # Capture while still attached to a session
            entry["groups"] = host_obj.groups
        calls.append(entry)
        return True

    with patch(target, side_effect=side_effect):
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

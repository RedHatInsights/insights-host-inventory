import json
import os
from collections import namedtuple
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock
from uuid import UUID

from confluent_kafka import TopicPartition

from app.auth.identity import Identity
from app.auth.identity import to_auth_header
from app.common import inventory_config
from app.culling import CONVENTIONAL_TIME_TO_DELETE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
from app.models import Host
from app.serialization import _deserialize_tags
from app.serialization import serialize_facts
from app.serialization import serialize_uuid
from app.utils import Tag
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import minimal_host

MockFutureCallback = namedtuple("MockFutureCallback", ("method", "args", "kwargs", "extra_arg"))


class MockEventProducer:
    def __init__(self):
        self.event = None
        self.key = None
        self.headers = None
        self.topic = None
        self.wait = None
        self._kafka_producer = Mock()
        self._kafka_producer.flush = Mock(return_value=True)

    def write_event(self, event, key, headers, wait=False):
        self.event = event
        self.key = key
        self.headers = headers
        self.wait = wait


class FakeMessage:
    def __init__(self, error=None, message=None):
        self.message = message or json.dumps({"platform_metadata": {"request_id": generate_uuid()}})
        self._error = error

    def value(self):
        return self.message

    def error(self):
        return self._error

    def partition(self):
        return 0

    def offset(self):
        return 0


class MockFuture:
    def __init__(self):
        self.callbacks = []
        self.errbacks = []

    @staticmethod
    def _fire(source):
        for callback in source:
            args = callback.args + (callback.extra_arg,)
            callback.method(*args, **callback.kwargs)

    @staticmethod
    def _add(target, args, kwargs):
        item = MockFutureCallback(args[0], args[1:], kwargs, object())
        target.append(item)

    def add_callback(self, *args, **kwargs):
        self._add(self.callbacks, args, kwargs)

    def add_errback(self, *args, **kwargs):
        self._add(self.errbacks, args, kwargs)

    def success(self):
        self._fire(self.callbacks)

    def failure(self):
        self._fire(self.errbacks)


def generate_kessel_workspace_message(
    operation: str, id: str, name: str, type: str = "standard", identity: dict = SYSTEM_IDENTITY
):
    now = datetime.now().isoformat()

    payload_dict = {
        "operation": operation,
        "org_id": identity["org_id"],
        "account_number": identity["account_number"],
        "workspace": {
            "id": id,
            "name": name,
            "type": type,
            "created": now,
            "modified": now,
        },
    }

    return {
        "schema": {"type": "string", "optional": False, "name": "io.debezium.data.Json", "version": 1},
        "payload": json.dumps(payload_dict),
    }


def wrap_message(host_data, operation="add_host", platform_metadata=None, operation_args=None):
    message = {"operation": operation, "data": host_data}

    if platform_metadata:
        message["platform_metadata"] = platform_metadata

    if operation_args:
        message["operation_args"] = operation_args

    return message


def assert_mq_host_data(actual_id: str, actual_event: dict, expected_results: dict, host_keys_to_check: list[str]):
    """
    Assert that MQ host data matches expected results.

    Special handling for system_profile: When backward compatibility is enabled,
    the actual event may contain legacy fields (e.g., 'ansible', 'sap_system') in addition
    to the 'workloads' structure. This function compares the 'workloads' data specifically
    and ignores legacy backward compatibility fields in the actual event.
    """
    assert actual_event["host"]["id"] == actual_id

    for key in host_keys_to_check:
        if key == "system_profile":
            # Special comparison for system_profile to handle backward compatibility
            actual_sp = actual_event["host"]["system_profile"]
            expected_sp = expected_results["host"]["system_profile"]

            # Compare all fields that exist in expected results
            for expected_key, expected_value in expected_sp.items():
                assert expected_key in actual_sp, f"Expected key '{expected_key}' not found in actual system_profile"
                assert actual_sp[expected_key] == expected_value, (
                    f"system_profile['{expected_key}'] mismatch: "
                    f"expected {expected_value}, got {actual_sp[expected_key]}"
                )
        else:
            assert actual_event["host"][key] == expected_results["host"][key]


def assert_delete_event_is_valid(
    event_producer,
    host,
    timestamp,
    expected_request_id=None,
    expected_metadata=None,
    identity=USER_IDENTITY,
    initiated_by_frontend=False,
):
    event = json.loads(event_producer.event)

    assert isinstance(event, dict)

    expected_keys = {
        "timestamp",
        "type",
        "id",
        "account",
        "org_id",
        "insights_id",
        "request_id",
        "subscription_manager_id",
        "initiated_by_frontend",
        "platform_metadata",
        "metadata",
    }
    assert set(event.keys()) == expected_keys

    assert timestamp.replace(tzinfo=UTC).isoformat() == event["timestamp"]

    assert event["type"] == "delete"

    assert serialize_uuid(host.insights_id) == event["insights_id"]

    assert event["initiated_by_frontend"] is initiated_by_frontend

    if initiated_by_frontend:
        assert event["subscription_manager_id"] is not None

    assert event_producer.key == str(host.id)
    assert event_producer.headers == expected_headers(
        "delete",
        event["request_id"],
        serialize_uuid(host.insights_id),
        host.reporter,
        host.system_profile_facts.get("host_type"),
        host.system_profile_facts.get("operating_system", {}).get("name"),
    )

    if identity:
        assert event["platform_metadata"] == {"b64_identity": to_auth_header(Identity(obj=identity))}

    if expected_request_id:
        assert event["request_id"] == expected_request_id

    if expected_metadata:
        assert event["metadata"] == expected_metadata


def assert_delete_notification_is_valid(notification_event_producer, host):
    event = json.loads(notification_event_producer.event)

    assert isinstance(event, dict)

    expected_keys = {
        "timestamp",
        "event_type",
        "org_id",
        "application",
        "bundle",
        "context",
        "events",
    }
    assert set(event.keys()) == expected_keys

    assert event["event_type"] == "system-deleted"

    assert serialize_uuid(host.insights_id) == event["events"][0]["payload"]["insights_id"]


def _assert_stale_notification_headers(headers: dict[str, Any] | None, event_type: str) -> None:
    """Validate notification headers structure and content."""
    assert headers is not None, "Headers should not be None"
    assert isinstance(headers, dict), f"Headers should be a dict, got: {type(headers)}"

    # Stale notifications don't include request_id (job-triggered, not request-triggered)
    expected_header_keys = {"event_type", "producer", "rh-message-id"}
    assert set(headers.keys()) == expected_header_keys, f"Header keys mismatch: {set(headers.keys())}"

    assert headers["event_type"] == event_type, f"Header event_type mismatch: {headers['event_type']} != {event_type}"
    # Producer is the hostname of the machine running the code
    assert headers["producer"], "Producer header should not be empty"

    # Validate rh-message-id is a valid UUID
    try:
        UUID(headers["rh-message-id"])
    except ValueError as err:
        raise AssertionError(f"rh-message-id is not a valid UUID: {headers['rh-message-id']}") from err


def _assert_stale_notification_context(context: dict[str, Any], host: Host) -> None:
    """Validate notification context structure and content."""
    expected_context_keys = {
        "inventory_id",
        "hostname",
        "display_name",
        "rhel_version",
        "tags",
        "host_url",
    }
    assert set(context.keys()) == expected_context_keys, f"Context keys mismatch: {set(context.keys())}"

    # Verify context field values
    assert context["inventory_id"] == str(host.id)
    assert context["display_name"] == host.display_name
    assert context["hostname"] == host.canonical_facts.get("fqdn", "")

    # Validate host_url
    expected_host_url = f"{inventory_config().base_ui_url}/{host.id}"
    assert context["host_url"] == expected_host_url, f"host_url mismatch: {context['host_url']} != {expected_host_url}"

    # rhel_version is only populated for RHEL hosts
    # Get operating_system from the static_system_profile relationship
    os_info = {}
    if host.static_system_profile and host.static_system_profile.operating_system:
        os_info = host.static_system_profile.operating_system

    if os_info.get("name", "").lower() == "rhel":
        expected_version = f"{os_info.get('major')}.{os_info.get('minor')}"
        assert context["rhel_version"] == expected_version
    else:
        assert context["rhel_version"] == ""

    # Validate tags
    expected_tags = _deserialize_tags(host.tags)
    assert context["tags"] == expected_tags, f"Tags mismatch: {context['tags']} != {expected_tags}"


def _assert_stale_notification_payload(payload: dict[str, Any], host: Host) -> None:
    """Validate notification payload structure and content."""
    expected_payload_keys = {
        "insights_id",
        "subscription_manager_id",
        "satellite_id",
        "groups",
    }
    assert set(payload.keys()) == expected_payload_keys, f"Payload keys mismatch: {set(payload.keys())}"

    # Verify payload field values
    assert payload["insights_id"] == host.canonical_facts.get("insights_id", "")
    assert payload["subscription_manager_id"] == host.canonical_facts.get("subscription_manager_id", "")
    assert payload["satellite_id"] == host.canonical_facts.get("satellite_id", "")

    # Verify groups - a host can have at most 1 group
    expected_groups = host.groups or []
    payload_groups = payload.get("groups", [])
    assert len(payload_groups) <= 1
    assert len(payload_groups) == len(expected_groups)
    if expected_groups:
        assert payload_groups[0]["id"] == expected_groups[0].get("id")
        assert payload_groups[0]["name"] == expected_groups[0].get("name")


def assert_stale_notification_is_valid(notification_event_producer: MockEventProducer, host: Host) -> None:
    """
    Validate stale notification structure and content, including headers.

    Args:
        notification_event_producer: The mock event producer containing the notification
        host: The host object to validate against
    """
    # Validate headers
    _assert_stale_notification_headers(notification_event_producer.headers, "system-became-stale")

    # Validate event body
    event = json.loads(notification_event_producer.event)
    assert isinstance(event, dict)

    # Validate root level keys
    expected_root_keys = {
        "timestamp",
        "event_type",
        "org_id",
        "application",
        "bundle",
        "context",
        "events",
    }
    assert set(event.keys()) == expected_root_keys, f"Root keys mismatch: {set(event.keys())}"

    # Verify root level fields
    assert event["event_type"] == "system-became-stale"
    assert event["org_id"] == host.org_id
    assert event["application"] == "inventory"
    assert event["bundle"] == "rhel"

    # Validate timestamp format and approximate value (within 10 seconds from now)
    event_timestamp = event["timestamp"]
    try:
        parsed_timestamp = datetime.fromisoformat(event_timestamp.replace("Z", "+00:00"))
    except ValueError as err:
        raise AssertionError(f"Timestamp is not in correct ISO format: {event_timestamp}") from err

    now = datetime.now(UTC)
    time_diff = abs((now - parsed_timestamp).total_seconds())
    assert time_diff < 10, f"Timestamp {parsed_timestamp} is more than 10 seconds from now ({now})"

    # Validate context
    _assert_stale_notification_context(event["context"], host)

    # Validate events structure
    assert isinstance(event["events"], list)
    assert len(event["events"]) == 1

    event_item = event["events"][0]
    expected_event_keys = {"metadata", "payload"}
    assert set(event_item.keys()) == expected_event_keys, f"Event keys mismatch: {set(event_item.keys())}"

    # Validate metadata is empty dict
    assert event_item["metadata"] == {}, f"Metadata should be empty dict, got: {event_item['metadata']}"

    # Validate payload
    _assert_stale_notification_payload(event_item["payload"], host)


def assert_patch_event_is_valid(
    host,
    event_producer,
    expected_request_id,
    expected_timestamp,
    display_name="patch_event_test",
    stale_timestamp=None,
    reporter=None,
    identity=USER_IDENTITY,
):
    stale_timestamp = (
        host.last_check_in.astimezone(UTC) + timedelta(seconds=CONVENTIONAL_TIME_TO_STALE_SECONDS)
    ).isoformat()
    stale_warning_timestamp = (
        host.last_check_in.astimezone(UTC) + timedelta(seconds=CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS)
    ).isoformat()
    culled_timestamp = (
        host.last_check_in.astimezone(UTC) + timedelta(seconds=CONVENTIONAL_TIME_TO_DELETE_SECONDS)
    ).isoformat()

    reporter = reporter or host.reporter

    event = json.loads(event_producer.event)

    assert isinstance(event, dict)

    expected_event = {
        "type": "updated",
        "host": {
            "id": str(host.id),
            "org_id": host.org_id,
            "account": host.account,
            "display_name": display_name,
            "ansible_host": host.ansible_host,
            "fqdn": host.fqdn,
            "groups": host.groups,
            "insights_id": serialize_uuid(host.insights_id),
            "bios_uuid": host.bios_uuid,
            "ip_addresses": host.ip_addresses,
            "mac_addresses": host.mac_addresses,
            "facts": serialize_facts(host.facts),
            "satellite_id": host.satellite_id,
            "subscription_manager_id": host.subscription_manager_id,
            "system_profile": host.system_profile_facts,
            "per_reporter_staleness": host.per_reporter_staleness,
            "tags": [tag.data() for tag in Tag.create_tags_from_nested(host.tags)],
            "reporter": reporter,
            "stale_timestamp": stale_timestamp,
            "stale_warning_timestamp": stale_warning_timestamp,
            "culled_timestamp": culled_timestamp,
            "created": host.created_on.astimezone(UTC).isoformat(),
            "last_check_in": host.last_check_in.isoformat(),
            "provider_id": host.provider_id,
            "provider_type": host.provider_type,
            "openshift_cluster_id": host.openshift_cluster_id,
        },
        "platform_metadata": {"b64_identity": to_auth_header(Identity(obj=identity))},
        "metadata": {"request_id": expected_request_id},
        "timestamp": expected_timestamp.isoformat(),
    }

    # We don't have this information without retrieving the host after the patch request
    del event["host"]["updated"]

    assert event == expected_event
    assert event_producer.key == str(host.id)
    assert event_producer.headers == expected_headers(
        "updated",
        expected_request_id,
        serialize_uuid(host.insights_id),
        host.reporter,
        host.system_profile_facts.get("host_type"),
        host.system_profile_facts.get("operating_system", {}).get("name"),
    )


def assert_system_registered_notification_is_valid(notification_event_producer, host):
    event = json.loads(notification_event_producer.event)
    context = event["context"]

    assert isinstance(event, dict)

    expected_keys = {
        "timestamp",
        "event_type",
        "org_id",
        "application",
        "bundle",
        "context",
        "events",
    }

    expected_context_keys = {
        "inventory_id",
        "hostname",
        "display_name",
        "rhel_version",
        "tags",
        "host_url",
    }

    expected_payload_keys = {
        "insights_id",
        "subscription_manager_id",
        "satellite_id",
        "groups",
        "reporter",
        "system_check_in",
    }
    assert set(event.keys()) == expected_keys
    assert set(context.keys()) == expected_context_keys
    assert context["host_url"].endswith(f"/insights/inventory/{context['inventory_id']}")
    assert event["event_type"] == "new-system-registered"

    for item in event["events"]:
        payload = item["payload"]
        assert set(payload.keys()) == expected_payload_keys
        assert serialize_uuid(host.insights_id) == payload["insights_id"]
        assert isinstance(datetime.fromisoformat(payload["system_check_in"]), datetime)


def expected_headers(
    event_type, request_id, insights_id=None, reporter=None, host_type=None, os_name=None, is_bootc="False"
):
    return {
        "event_type": event_type,
        "request_id": request_id,
        "producer": os.uname().nodename,
        "insights_id": insights_id,
        "reporter": reporter,
        "host_type": host_type,
        "os_name": os_name,
        "is_bootc": is_bootc,
    }


def expected_encoded_headers(event_type, request_id, insights_id=None, reporter=None, host_type=None, os_name=None):
    return [
        ("event_type", event_type.name.encode("utf-8")),
        ("request_id", request_id.encode("utf-8")),
        ("producer", os.uname().nodename.encode("utf-8")),
        ("insights_id", insights_id.encode("utf-8")),
        ("reporter", reporter.encode("utf-8")),
        ("host_type", host_type.encode("utf-8")),
        ("os_name", os_name.encode("utf-8")),
    ]


def assert_synchronize_event_is_valid(
    event_producer, key, host, groups, timestamp, expected_request_id=None, expected_metadata=None
):
    event = json.loads(event_producer.event)

    assert key == event_producer.key
    assert isinstance(event, dict)
    expected_keys = {"metadata", "timestamp", "host", "platform_metadata", "type"}

    assert set(event.keys()) == expected_keys
    assert timestamp.replace(tzinfo=UTC).isoformat() == event["timestamp"]
    assert event["type"] == "updated"
    assert serialize_uuid(host.insights_id) == event["host"]["insights_id"]
    assert str(host.id) in event_producer.key

    # Assert groups data
    if groups == []:
        assert event["host"]["groups"] == []
    else:
        assert event["host"]["groups"][0]["id"] == str(groups[0].id)
        assert event["host"]["groups"][0]["name"] == groups[0].name
        assert event["host"]["groups"][0]["ungrouped"] == groups[0].ungrouped

    assert event_producer.headers == expected_headers(
        "updated",
        event["metadata"]["request_id"],
        serialize_uuid(host.insights_id),
        host.reporter,
        host.system_profile_facts.get("host_type"),
        host.system_profile_facts.get("operating_system", {}).get("name"),
    )

    if expected_request_id:
        assert event["request_id"] == expected_request_id

    if expected_metadata:
        assert event["metadata"] == expected_metadata


def create_kafka_consumer_mock(
    mocker, topic, number_of_partitions, messages_per_partition, number_of_polls=5, message_list=None
):
    fake_consumer = mocker.Mock()
    mock_consume = []
    poll_result_list = []
    mock_start_offsets = {}
    partitions_dict = {}
    partitions = []

    for partition_id in range(number_of_partitions):
        partition = TopicPartition(topic, partition_id)
        partitions_dict[partition_id] = partition
        partitions.append(partition)

    fake_consumer.list_topics.return_value = SimpleNamespace(
        topics={topic: SimpleNamespace(partitions=partitions_dict)}
    )

    fake_consumer.partitions_for_topic.return_value = set(range(number_of_partitions))
    fake_consumer.assignment.return_value = set(partitions)

    if message_list:
        mock_consume = [mocker.Mock(**{"value.return_value": message}) for message in message_list]
    else:
        mock_consume = [
            mocker.Mock(**{"value.return_value": json.dumps(wrap_message(minimal_host().data()))})
            for _ in range(number_of_partitions * messages_per_partition)
        ]

    for partition in partitions:
        mock_start_offsets[partition] = SimpleNamespace(offset=1)

    poll_result_list.extend([mock_consume] * number_of_polls)
    poll_result_list.append({})

    fake_consumer.consume.side_effect = poll_result_list
    fake_consumer.offsets_for_times.return_value = mock_start_offsets
    return fake_consumer

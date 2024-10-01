import json
import os
from collections import namedtuple
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from types import SimpleNamespace
from unittest.mock import Mock

from confluent_kafka import TopicPartition

from app.auth.identity import Identity
from app.auth.identity import to_auth_header
from app.serialization import serialize_facts
from app.utils import Tag
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import minimal_host
from tests.helpers.test_utils import USER_IDENTITY


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


def wrap_message(host_data, operation="add_host", platform_metadata=None, operation_args=None):
    message = {"operation": operation, "data": host_data}

    if platform_metadata:
        message["platform_metadata"] = platform_metadata

    if operation_args:
        message["operation_args"] = operation_args

    return message


def assert_mq_host_data(actual_id, actual_event, expected_results, host_keys_to_check):
    assert actual_event["host"]["id"] == actual_id

    for key in host_keys_to_check:
        assert actual_event["host"][key] == expected_results["host"][key]


def assert_delete_event_is_valid(
    event_producer, host, timestamp, expected_request_id=None, expected_metadata=None, identity=USER_IDENTITY
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
        "platform_metadata",
        "metadata",
    }
    assert set(event.keys()) == expected_keys

    assert timestamp.replace(tzinfo=timezone.utc).isoformat() == event["timestamp"]

    assert "delete" == event["type"]

    assert host.canonical_facts.get("insights_id") == event["insights_id"]

    assert event_producer.key == str(host.id)
    assert event_producer.headers == expected_headers(
        "delete",
        event["request_id"],
        host.canonical_facts.get("insights_id"),
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

    assert "system-deleted" == event["event_type"]

    assert host.canonical_facts.get("insights_id") == event["events"][0]["payload"]["insights_id"]


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
    stale_timestamp = (host.modified_on.astimezone(timezone.utc) + timedelta(seconds=104400)).isoformat()
    stale_warning_timestamp = (host.modified_on.astimezone(timezone.utc) + timedelta(seconds=604800)).isoformat()
    culled_timestamp = (host.modified_on.astimezone(timezone.utc) + timedelta(seconds=1209600)).isoformat()
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
            "fqdn": host.canonical_facts.get("fqdn"),
            "groups": host.groups,
            "insights_id": host.canonical_facts.get("insights_id"),
            "bios_uuid": host.canonical_facts.get("bios_uuid"),
            "ip_addresses": host.canonical_facts.get("ip_addresses"),
            "mac_addresses": host.canonical_facts.get("mac_addresses"),
            "facts": serialize_facts(host.facts),
            "satellite_id": host.canonical_facts.get("satellite_id"),
            "subscription_manager_id": host.canonical_facts.get("subscription_manager_id"),
            "system_profile": host.system_profile_facts,
            "per_reporter_staleness": host.per_reporter_staleness,
            "tags": [tag.data() for tag in Tag.create_tags_from_nested(host.tags)],
            "reporter": reporter,
            "stale_timestamp": stale_timestamp,
            "stale_warning_timestamp": stale_warning_timestamp,
            "culled_timestamp": culled_timestamp,
            "created": host.created_on.astimezone(timezone.utc).isoformat(),
            "provider_id": host.canonical_facts.get("provider_id"),
            "provider_type": host.canonical_facts.get("provider_type"),
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
        host.canonical_facts.get("insights_id"),
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
    assert "new-system-registered" == event["event_type"]

    for item in event["events"]:
        payload = item["payload"]
        assert set(payload.keys()) == expected_payload_keys
        assert host.insights_id == payload["insights_id"]
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
    event_producer, key, host, timestamp, expected_request_id=None, expected_metadata=None
):
    event = json.loads(event_producer.event)

    assert key == event_producer.key
    assert isinstance(event, dict)
    expected_keys = {"metadata", "timestamp", "host", "platform_metadata", "type"}

    assert set(event.keys()) == expected_keys
    assert timestamp.replace(tzinfo=timezone.utc).isoformat() == event["timestamp"]
    assert "updated" == event["type"]
    assert host.canonical_facts.get("insights_id") == event["host"]["insights_id"]
    assert str(host.id) in event_producer.key
    assert event_producer.headers == expected_headers(
        "updated",
        event["metadata"]["request_id"],
        host.canonical_facts.get("insights_id"),
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

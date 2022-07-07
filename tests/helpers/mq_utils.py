import json
import os
from collections import namedtuple
from datetime import timedelta
from datetime import timezone
from types import SimpleNamespace
from unittest.mock import Mock

from kafka import TopicPartition

from app.utils import Tag
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


def wrap_message(host_data, operation="add_host", platform_metadata=None):
    message = {"operation": operation, "data": host_data}

    if platform_metadata:
        message["platform_metadata"] = platform_metadata

    return message


def assert_mq_host_data(actual_id, actual_event, expected_results, host_keys_to_check):
    assert actual_event["host"]["id"] == actual_id

    for key in host_keys_to_check:
        assert actual_event["host"][key] == expected_results["host"][key]


def assert_delete_event_is_valid(event_producer, host, timestamp, expected_request_id=None, expected_metadata=None):
    event = json.loads(event_producer.event)

    assert isinstance(event, dict)

    expected_keys = {"timestamp", "type", "id", "org_id", "insights_id", "request_id", "metadata"}
    assert set(event.keys()) == expected_keys

    assert timestamp.replace(tzinfo=timezone.utc).isoformat() == event["timestamp"]

    assert "delete" == event["type"]

    assert host.canonical_facts.get("insights_id") == event["insights_id"]

    assert event_producer.key == str(host.id)
    assert event_producer.headers == expected_headers(
        "delete", event["request_id"], host.canonical_facts.get("insights_id")
    )

    if expected_request_id:
        assert event["request_id"] == expected_request_id

    if expected_metadata:
        assert event["metadata"] == expected_metadata


def assert_patch_event_is_valid(
    host,
    event_producer,
    expected_request_id,
    expected_timestamp,
    display_name="patch_event_test",
    stale_timestamp=None,
    reporter=None,
):
    stale_timestamp = stale_timestamp or host.stale_timestamp.astimezone(timezone.utc)
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
            "insights_id": host.canonical_facts.get("insights_id"),
            "bios_uuid": host.canonical_facts.get("bios_uuid"),
            "ip_addresses": host.canonical_facts.get("ip_addresses"),
            "mac_addresses": host.canonical_facts.get("mac_addresses"),
            "satellite_id": host.canonical_facts.get("satellite_id"),
            "subscription_manager_id": host.canonical_facts.get("subscription_manager_id"),
            "system_profile": host.system_profile_facts,
            "per_reporter_staleness": host.per_reporter_staleness,
            "tags": [tag.data() for tag in Tag.create_tags_from_nested(host.tags)],
            "reporter": reporter,
            "stale_timestamp": stale_timestamp.isoformat(),
            "stale_warning_timestamp": (stale_timestamp + timedelta(weeks=1)).isoformat(),
            "culled_timestamp": (stale_timestamp + timedelta(weeks=2)).isoformat(),
            "created": host.created_on.astimezone(timezone.utc).isoformat(),
            "provider_id": host.canonical_facts.get("provider_id"),
            "provider_type": host.canonical_facts.get("provider_type"),
        },
        "platform_metadata": None,
        "metadata": {"request_id": expected_request_id},
        "timestamp": expected_timestamp.isoformat(),
    }

    # We don't have this information without retrieving the host after the patch request
    del event["host"]["updated"]

    assert event == expected_event
    assert event_producer.key == str(host.id)
    assert event_producer.headers == expected_headers(
        "updated", expected_request_id, host.canonical_facts.get("insights_id")
    )


def expected_headers(event_type, request_id, insights_id):
    return {
        "event_type": event_type,
        "request_id": request_id,
        "producer": os.uname().nodename,
        "insights_id": insights_id,
    }


def expected_encoded_headers(event_type, request_id, insights_id):
    return [
        ("event_type", event_type.name.encode("utf-8")),
        ("request_id", request_id.encode("utf-8")),
        ("producer", os.uname().nodename.encode("utf-8")),
        ("insights_id", insights_id.encode("utf-8")),
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
        "updated", event["metadata"]["request_id"], host.canonical_facts.get("insights_id")
    )

    if expected_request_id:
        assert event["request_id"] == expected_request_id

    if expected_metadata:
        assert event["metadata"] == expected_metadata


def create_kafka_consumer_mock(
    mocker, config, number_of_partitions, messages_per_partition, number_of_polls=5, message_list=None
):
    fake_consumer = mocker.Mock()
    mock_poll = {}
    poll_result_list = []
    mock_start_offsets = {}
    mock_end_offsets = {}
    partitions = []

    fake_consumer.topics.return_value = {config.host_ingress_topic}

    for partition_id in range(number_of_partitions):
        partitions.append(TopicPartition(config.host_ingress_topic, partition_id))

    fake_consumer.partitions_for_topic.return_value = set(range(number_of_partitions))
    fake_consumer.assignment.return_value = set(partitions)

    for partition in partitions:
        if message_list:
            mock_poll[partition] = [SimpleNamespace(value=message) for message in message_list]
        else:
            mock_poll[partition] = [
                SimpleNamespace(value=json.dumps(wrap_message(minimal_host().data())))
                for _ in range(messages_per_partition)
            ]
        mock_start_offsets[partition] = SimpleNamespace(offset=1)
        mock_end_offsets[partition] = 100

    poll_result_list.extend([mock_poll] * number_of_polls)
    poll_result_list.append({})

    fake_consumer.poll.side_effect = poll_result_list
    fake_consumer.offsets_for_times.return_value = mock_start_offsets
    fake_consumer.end_offsets.return_value = mock_end_offsets
    fake_consumer.position.return_value = 1
    return fake_consumer

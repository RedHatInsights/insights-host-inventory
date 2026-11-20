"""Ingress argument/deferral contracts with small, fully compared profiles."""

import json
from copy import deepcopy
from datetime import datetime
from datetime import timedelta

import pytest
from marshmallow import ValidationError

from app.queue.host_mq import IngressMessageConsumer
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.api_utils import build_system_profile_url
from tests.helpers.mq_utils import FakeMessage
from tests.helpers.mq_utils import mq_service_host_listeners
from tests.helpers.mq_utils import wrap_message
from tests.helpers.test_utils import OWNER_ID
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import get_platform_metadata
from tests.helpers.test_utils import minimal_host
from tests.helpers.test_utils import now

ORIGINAL_PROFILE = {
    "owner_id": OWNER_ID,
    "arch": "x86_64",
    "number_of_cpus": 2,
    "running_processes": ["sshd", "original-process"],
    "network_interfaces": [{"name": "eth0", "ipv4_addresses": ["192.0.2.1"], "state": "UP"}],
}
INCOMING_PROFILE = {
    "owner_id": OWNER_ID,
    "arch": "aarch64",
    "number_of_cpus": 4,
    "running_processes": ["replacement-process"],
    "network_interfaces": [{"name": "eth1", "ipv4_addresses": ["192.0.2.2"], "state": "DOWN"}],
}


@pytest.fixture
def ingest_with_args(mocker, flask_app, event_producer_mock, notification_event_producer_mock):
    def ingest(host, operation_args=None):
        message = wrap_message(host.data(), platform_metadata=get_platform_metadata())
        # wrap_message omits falsey values: insert {} explicitly to test its wire contract.
        if operation_args is not None:
            message["operation_args"] = operation_args
        record = FakeMessage(message=json.dumps(message))
        fake_consumer = mocker.Mock(**{"consume.return_value": [record]})
        consumer = IngressMessageConsumer(
            fake_consumer, flask_app, event_producer_mock, notification_event_producer_mock
        )
        event_producer_mock.event = None
        with mq_service_host_listeners():
            consumer.event_loop(mocker.Mock(side_effect=(False, True)))
        assert event_producer_mock.event is not None
        return json.loads(event_producer_mock.event)

    return ingest


def _assert_host_and_profile(api_get, event, host_id, reporter, ansible_host, profile):
    host = event["host"]
    assert host["id"] == host_id
    assert host["reporter"] == reporter
    assert host["ansible_host"] == ansible_host
    assert host["system_profile"] == profile
    status, response = api_get(build_hosts_url(host_list_or_id=host_id))
    assert status == 200
    assert len(response["results"]) == 1
    persisted = response["results"][0]
    assert persisted["id"] == host_id
    assert persisted["reporter"] == reporter
    assert persisted["ansible_host"] == ansible_host
    status, response = api_get(build_system_profile_url(host_id))
    assert status == 200
    assert len(response["results"]) == 1
    assert response["results"][0]["id"] == host_id
    # These profiles contain no date/legacy workload aliases or explicit nulls;
    # raw JSON therefore needs none of IQE's generated-SDK normalization.
    assert response["results"][0]["system_profile"] == profile


def test_operation_args_omitted_empty_and_unknown(ingest_with_args, api_get, subtests):
    for args in (None, {}, {"unknown-option": "ignored", "another-option": "also-ignored"}):
        with subtests.test(operation_args=args):
            host = minimal_host(
                insights_id=generate_uuid(),
                reporter="puptoo",
                ansible_host="original-ansible",
                system_profile=deepcopy(ORIGINAL_PROFILE),
            )
            created = ingest_with_args(host, args)
            assert created["type"] == "created"
            host_id = created["host"]["id"]
            _assert_host_and_profile(api_get, created, host_id, "puptoo", "original-ansible", ORIGINAL_PROFILE)
            host.reporter = "rhsm-system-profile-bridge"
            host.ansible_host = "replacement-ansible"
            host.system_profile = deepcopy(INCOMING_PROFILE)
            updated = ingest_with_args(host, args)
            assert updated["type"] == "updated"
            _assert_host_and_profile(api_get, updated, host_id, host.reporter, host.ansible_host, INCOMING_PROFILE)


def test_operation_args_wrong_type(mocker, flask_app, api_get, subtests):
    producer = mocker.Mock()
    for args in ("not-a-dictionary", ["not-a-dictionary"], [{}]):
        with subtests.test(operation_args=args):
            host = minimal_host(insights_id=generate_uuid())
            message = wrap_message(host.data(), platform_metadata=get_platform_metadata())
            message["operation_args"] = args
            fake_consumer = mocker.Mock(**{"consume.return_value": [FakeMessage(message=json.dumps(message))]})
            consumer = IngressMessageConsumer(fake_consumer, flask_app, producer, mocker.Mock())
            handler = mocker.spy(consumer, "handle_message")
            consumer.event_loop(mocker.Mock(side_effect=(False, True)))
            assert isinstance(handler.spy_exception, ValidationError)
            assert "operation_args" in handler.spy_exception.messages
            producer.write_event.assert_not_called()
            status, response = api_get(build_hosts_url(query=f"?insights_id={host.insights_id}"))
            assert status == 200
            assert response["results"] == []


def test_defer_to_fresh_reporter(ingest_with_args, api_get, subtests):
    for original_reporter, incoming_reporter in (
        ("puptoo", "rhsm-system-profile-bridge"),
        ("rep1", "rep2"),
        ("puptoo", "puptoo"),
    ):
        with subtests.test(original=original_reporter, incoming=incoming_reporter):
            host = minimal_host(
                insights_id=generate_uuid(),
                reporter=original_reporter,
                ansible_host="original-ansible",
                system_profile=deepcopy(ORIGINAL_PROFILE),
            )
            created = ingest_with_args(host)
            host.reporter = incoming_reporter
            host.ansible_host = "replacement-ansible"
            host.system_profile = deepcopy(INCOMING_PROFILE)
            updated = ingest_with_args(host, {"defer_to_reporter": original_reporter})
            assert updated["type"] == "updated"
            _assert_host_and_profile(
                api_get, updated, created["host"]["id"], incoming_reporter, host.ansible_host, ORIGINAL_PROFILE
            )


def test_defer_to_previous_reporter(ingest_with_args, api_get, subtests):
    for intermediate_reporter in ("rhsm-system-profile-bridge", "reporter2"):
        with subtests.test(intermediate=intermediate_reporter):
            host = minimal_host(
                insights_id=generate_uuid(),
                reporter="puptoo",
                ansible_host="original-ansible",
                system_profile=deepcopy(ORIGINAL_PROFILE),
            )
            created = ingest_with_args(host)
            host_id = created["host"]["id"]
            host.reporter = intermediate_reporter
            intermediate = ingest_with_args(host)
            assert intermediate["host"]["id"] == host_id
            assert intermediate["host"]["reporter"] == intermediate_reporter
            assert "puptoo" in intermediate["host"]["per_reporter_staleness"]
            host.reporter = "rhsm-system-profile-bridge"
            host.ansible_host = "replacement-ansible"
            host.system_profile = deepcopy(INCOMING_PROFILE)
            updated = ingest_with_args(host, {"defer_to_reporter": "puptoo"})
            _assert_host_and_profile(api_get, updated, host_id, host.reporter, host.ansible_host, ORIGINAL_PROFILE)


def test_defer_to_stale_reporter(mocker, ingest_with_args, api_get, api_create_staleness, subtests):
    status, _ = api_create_staleness(
        {
            "conventional_time_to_stale": 5,
            "conventional_time_to_stale_warning": 10,
            "conventional_time_to_delete": 3600,
        }
    )
    assert status == 201
    start = now() - timedelta(seconds=30)
    clock = mocker.patch("app.models.utils.datetime")
    for state, seconds in (("stale", 6), ("stale_warning", 11)):
        for refresh_host in (False, True):
            with subtests.test(state=state, refresh_host=refresh_host):
                clock.now.return_value = start
                host = minimal_host(
                    insights_id=generate_uuid(),
                    reporter="puptoo",
                    ansible_host="original-ansible",
                    system_profile=deepcopy(ORIGINAL_PROFILE),
                )
                created = ingest_with_args(host)
                prs = created["host"]["per_reporter_staleness"]["puptoo"]
                assert datetime.fromisoformat(prs["stale_timestamp"]) == start + timedelta(seconds=5)
                assert datetime.fromisoformat(prs["stale_warning_timestamp"]) == start + timedelta(seconds=10)
                threshold = datetime.fromisoformat(prs[f"{state}_timestamp"])
                clock.now.return_value = start + timedelta(seconds=seconds)
                if refresh_host:
                    host.reporter = "reporter2"
                    refreshed = ingest_with_args(host)
                    assert refreshed["host"]["per_reporter_staleness"]["puptoo"] == prs
                    assert datetime.fromisoformat(refreshed["host"]["stale_timestamp"]) > clock.now.return_value
                host.reporter = "rhsm-system-profile-bridge"
                host.ansible_host = "replacement-ansible"
                host.system_profile = deepcopy(INCOMING_PROFILE)
                updated = ingest_with_args(host, {"defer_to_reporter": "puptoo"})
                _assert_host_and_profile(
                    api_get, updated, created["host"]["id"], host.reporter, host.ansible_host, INCOMING_PROFILE
                )
                assert datetime.fromisoformat(updated["host"]["updated"]) > threshold


def test_defer_to_absent_reporter_and_unrelated_host(ingest_with_args, api_get):
    host = minimal_host(
        insights_id=generate_uuid(),
        reporter="reporter1",
        ansible_host="original-ansible",
        system_profile=deepcopy(ORIGINAL_PROFILE),
    )
    created = ingest_with_args(host)
    assert "puptoo" not in created["host"]["per_reporter_staleness"]
    host.reporter = "rhsm-system-profile-bridge"
    host.ansible_host = "replacement-ansible"
    host.system_profile = deepcopy(INCOMING_PROFILE)
    updated = ingest_with_args(host, {"defer_to_reporter": "puptoo"})
    _assert_host_and_profile(
        api_get, updated, created["host"]["id"], host.reporter, host.ansible_host, INCOMING_PROFILE
    )

    puptoo = ingest_with_args(
        minimal_host(insights_id=generate_uuid(), reporter="puptoo", system_profile=deepcopy(ORIGINAL_PROFILE))
    )
    unrelated = minimal_host(
        insights_id=generate_uuid(),
        reporter="rhsm-system-profile-bridge",
        ansible_host="unrelated-ansible",
        system_profile=deepcopy(INCOMING_PROFILE),
    )
    event = ingest_with_args(unrelated, {"defer_to_reporter": "puptoo"})
    assert event["type"] == "created"
    assert event["host"]["id"] != puptoo["host"]["id"]
    _assert_host_and_profile(
        api_get, event, event["host"]["id"], unrelated.reporter, unrelated.ansible_host, INCOMING_PROFILE
    )

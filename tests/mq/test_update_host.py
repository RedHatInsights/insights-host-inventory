from __future__ import annotations

import json
import logging
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from connexion import FlaskApp
from pytest_mock import MockerFixture

from app.models import Host
from app.models import db
from app.queue.event_producer import EventProducer
from app.queue.events import EventType
from app.queue.host_mq import IngressMessageConsumer
from app.queue.host_mq import OperationResult
from app.queue.host_mq import WorkspaceMessageConsumer
from app.queue.host_mq import write_add_update_event_message
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.db_utils import create_reference_host_in_db
from tests.helpers.mq_utils import FakeMessage
from tests.helpers.mq_utils import generate_kessel_workspace_message
from tests.helpers.mq_utils import wrap_message
from tests.helpers.outbox_utils import capture_outbox_calls
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import generate_random_string
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import get_platform_metadata
from tests.helpers.test_utils import minimal_host
from tests.helpers.test_utils import now


def _change_case_of_outbox_fields(host_data: dict) -> dict:
    return {
        **host_data,
        "insights_id": host_data["insights_id"].upper(),
        "subscription_manager_id": host_data["subscription_manager_id"].upper(),
        "satellite_id": host_data["satellite_id"].upper(),
    }


def _change_irrelevant_outbox_fields(host_data: dict) -> dict:
    return {
        **host_data,
        "display_name": generate_random_string(),
        "fqdn": generate_random_string(),
        "reporter": "puptoo",
        "facts": [{"namespace": "some_namespace", "facts": {"key": "value"}}],
        "tags": [{"namespace": "some_namespace", "key": "key", "value": "value"}],
        "system_profile": {"arch": "x86_64", "number_of_cpus": 4},
    }


def test_update_display_name(mq_create_or_update_host, db_get_host_by_insights_id, api_get, subtests):
    # Exercise the field/reporter classes without resetting the DB for every pair.
    fields = ("display_name", "ansible_host", "fqdn", "bios_uuid", "satellite_id", "subscription_manager_id")
    pairs = [(reporter, field) for reporter in ("iqe-host-inventory", "yupana") for field in fields]
    pairs.append(("rhsm-conduit", "display_name"))
    for reporter, field in pairs:
        with subtests.test(reporter=reporter, field=field):
            host = minimal_host(
                insights_id=generate_uuid(),
                reporter="iqe-host-inventory",
                display_name="original-name",
                ansible_host="original-ansible",
                fqdn=generate_random_string(),
                bios_uuid=generate_uuid(),
                satellite_id=generate_uuid(),
                subscription_manager_id=generate_uuid(),
            )
            key, created, _ = mq_create_or_update_host(host, return_all_data=True)
            assert created["type"] == "created"
            replacement = generate_uuid() if field.endswith("id") else f"updated-{generate_random_string()}"
            setattr(host, field, replacement)
            host.reporter = reporter
            updated_key, updated, _ = mq_create_or_update_host(host, return_all_data=True)
            assert updated["type"] == "updated"
            assert updated_key == key == updated["host"]["id"] == created["host"]["id"]
            assert updated["host"][field] == replacement
            assert updated["host"]["reporter"] == reporter
            record = db_get_host_by_insights_id(host.insights_id)
            assert str(getattr(record, field)) == replacement
            status, response = api_get(build_hosts_url(host_list_or_id=key))
            assert status == 200
            assert len(response["results"]) == 1
            assert response["results"][0]["id"] == key
            assert response["results"][0][field] == replacement


def test_mq_service_does_not_load_api_host_listeners():
    # mq_service_host_listeners relies on this; api.staleness would freeze modified_on on MQ updates.
    script = (
        "import sys, inv_mq_service\n"
        "inv_mq_service.create_app(inv_mq_service.RuntimeEnvironment.SERVICE)\n"
        "assert 'api.staleness' not in sys.modules\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=Path(__file__).parents[2], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr[-2000:]


@pytest.mark.usefixtures("mq_service_host_listeners")
def test_mq_check_in_and_updated_timestamps(mocker, flask_app, event_producer_mock, api_get):
    def ingest(host):
        message = json.dumps(wrap_message(host.data(), platform_metadata=get_platform_metadata()))
        fake_consumer = mocker.Mock(**{"consume.return_value": [FakeMessage(message=message)]})
        consumer = IngressMessageConsumer(fake_consumer, flask_app, event_producer_mock, mocker.Mock())
        event_producer_mock.event = None
        consumer.event_loop(mocker.Mock(side_effect=(False, True)))
        assert event_producer_mock.event is not None
        return json.loads(event_producer_mock.event)

    start = now()
    clock = mocker.patch("app.models.utils.datetime")
    clock.now.return_value = start
    host = minimal_host(
        insights_id=generate_uuid(),
        reporter="iqe-host-inventory",
        system_profile={"arch": "x86_64", "number_of_cpus": 2},
    )
    created = ingest(host)
    status, response = api_get(build_hosts_url(host_list_or_id=created["host"]["id"]))
    assert status == 200
    assert len(response["results"]) == 1
    original = response["results"][0]
    for result in (created["host"], original):
        checked_in = datetime.fromisoformat(result["last_check_in"])
        updated = datetime.fromisoformat(result["updated"])
        assert abs(checked_in - updated) <= timedelta(milliseconds=100)
        assert start <= checked_in <= start + timedelta(milliseconds=100)
        assert start <= updated <= start + timedelta(milliseconds=100)

    clock.now.return_value = start + timedelta(hours=1)
    host.reporter = "rhsm-conduit"
    event = ingest(host)
    assert event["type"] == "updated"
    updated_host = event["host"]
    assert updated_host["id"] == original["id"]
    assert updated_host["created"] == original["created"]
    assert abs(
        datetime.fromisoformat(updated_host["last_check_in"]) - datetime.fromisoformat(updated_host["updated"])
    ) <= timedelta(milliseconds=100)
    for field in ("last_check_in", "updated"):
        assert datetime.fromisoformat(updated_host[field]) > datetime.fromisoformat(original[field])
        assert (
            start + timedelta(hours=1)
            <= datetime.fromisoformat(updated_host[field])
            <= start + timedelta(hours=1, milliseconds=100)
        )


def test_cant_update_host_groups_via_mq(
    mq_create_or_update_host,
    db_get_host,
    db_get_hosts_for_group,
    db_get_group_by_id,
    db_create_group_with_hosts,
    db_create_group,
):
    original_group = db_create_group_with_hosts("original_group", 1)
    host = db_get_hosts_for_group(original_group.id)[0]
    original_group_id = str(original_group.id)
    host_id = str(host.id)

    other_group = db_create_group("other_group")
    other_group_id = str(other_group.id)

    update_data = minimal_host(insights_id=str(host.insights_id))
    update_data.groups = [{"id": other_group_id, "name": "other_group", "ungrouped": False}]

    mq_create_or_update_host(update_data)

    retrieved_group = db_get_group_by_id(original_group.id)
    assert retrieved_group.name == "original_group"
    assert len(db_get_hosts_for_group(original_group.id)) == 1
    assert len(db_get_hosts_for_group(other_group.id)) == 0

    retrieved_host = db_get_host(host_id)
    assert len(retrieved_host.groups) == 1
    assert retrieved_host.groups[0]["id"] == original_group_id
    assert retrieved_host.groups[0]["name"] == "original_group"


@pytest.mark.parametrize(
    "build_update_data",
    (
        pytest.param(lambda host_data: host_data, id="identical payload"),
        pytest.param(_change_irrelevant_outbox_fields, id="irrelevant fields changed"),
        pytest.param(_change_case_of_outbox_fields, id="changed case only"),
    ),
)
def test_mq_update_host_without_relevant_changes_no_outbox(
    mocker: MockerFixture,
    event_producer: EventProducer,
    flask_app: FlaskApp,
    db_get_host: Callable[[str], Host | None],
    build_update_data: Callable[[dict], dict],
):
    """
    Re-reporting an existing host via MQ must not write an outbox entry (replicate the host to Kessel),
    unless one of the replicated fields (insights_id, subscription_manager_id, satellite_id,
    ansible_host) or the host's workspace changed.
    """
    host_data = minimal_host(
        insights_id=generate_uuid(),
        subscription_manager_id=generate_uuid(),
        satellite_id=generate_uuid(),
        ansible_host=generate_random_string(),
        fqdn=generate_random_string(),
    ).data()

    def process_message_in_batch(message_data: dict) -> None:
        msg = json.dumps(wrap_message(message_data, "add_host", get_platform_metadata()))
        fake_consumer = mocker.Mock(**{"consume.side_effect": [[FakeMessage(message=msg)]]})
        consumer = IngressMessageConsumer(fake_consumer, flask_app, event_producer, mocker.Mock())
        consumer.event_loop(mocker.Mock(side_effect=(False, True)))

    with capture_outbox_calls("lib.outbox_repository.write_event_to_outbox") as outbox_calls:
        process_message_in_batch(host_data)

    # Sanity check - creating the host is replicated, so the outbox calls are being captured
    assert len(outbox_calls) == 1
    assert outbox_calls[0]["event_type"] == EventType.created
    host_id = str(outbox_calls[0]["host_id"])
    created_host = db_get_host(host_id)
    assert created_host is not None
    original_last_check_in = created_host.last_check_in

    with capture_outbox_calls("lib.outbox_repository.write_event_to_outbox") as outbox_calls:
        process_message_in_batch(build_update_data(host_data))

    assert outbox_calls == []

    # Make sure the second message really updated the existing host instead of being skipped.
    # The MQ consumer commits in its own session, so drop the host cached in the test session first.
    db.session.expire_all()
    updated_host = db_get_host(host_id)
    assert updated_host is not None
    assert updated_host.last_check_in > original_last_check_in


def test_batch_mq_header_request_id_updates(mocker, flask_app):
    # Verifies that when messages are sent as part of the same batch,
    # the request_id used in the header is updated correctly.
    msg_list = []
    request_id_list = []
    for _ in range(5):
        metadata = get_platform_metadata()
        request_id = generate_uuid()
        metadata["request_id"] = request_id
        request_id_list.append(request_id)
        msg_list.append(
            json.dumps(
                wrap_message(
                    minimal_host().data(),
                    "add_host",
                    metadata,
                )
            )
        )

    # Patch batch settings in inventory_config()
    mocker.patch(
        "app.queue.host_mq.inventory_config",
        return_value=SimpleNamespace(
            mq_db_batch_max_messages=7,
            mq_db_batch_max_seconds=1,
            culling_stale_warning_offset_delta=1,
            culling_culled_offset_delta=1,
            conventional_time_to_stale_seconds=1,
            conventional_time_to_stale_warning_seconds=1,
            conventional_time_to_delete_seconds=1,
        ),
    )

    fake_consumer = mocker.Mock(
        **{
            "consume.side_effect": [
                [FakeMessage(message=msg_list[i]) for i in range(5)],
                [],
                [],
                [],
                [],
            ]
        }
    )

    event_producer_mock = mocker.Mock()
    send_notification_patch = mocker.patch("app.queue.host_mq.send_notification")

    consumer = IngressMessageConsumer(fake_consumer, flask_app, event_producer_mock, mocker.Mock())
    consumer.event_loop(mocker.Mock(side_effect=([False for _ in range(2)] + [True])))

    # Should have been called once per host
    assert send_notification_patch.call_count == 5
    assert event_producer_mock.write_event.call_count == 5

    for i in range(5):
        headers = event_producer_mock.write_event.call_args_list[i][0][2]
        assert headers["request_id"] == request_id_list[i]


def test_workspace_mq_update(
    mocker, flask_app, db_create_group_with_hosts, db_get_hosts_for_group, db_get_group_by_id
):
    group = db_create_group_with_hosts("original_group_name", 3)
    workspace_id = str(group.id)
    host_id_list = [str(host.id) for host in db_get_hosts_for_group(workspace_id)]

    new_name = "test-kessel-workspace"
    workspace_modified = "2025-06-01T10:30:00+00:00"
    message = generate_kessel_workspace_message("update", workspace_id, new_name, modified=workspace_modified)
    mock_event_producer = mocker.Mock()
    consumer = WorkspaceMessageConsumer(mocker.Mock(), flask_app, mock_event_producer, mocker.Mock())

    consumer.handle_message(json.dumps(message))
    found_group = db_get_group_by_id(workspace_id)

    assert found_group.name == new_name
    assert found_group.modified_on == datetime.fromisoformat(workspace_modified)

    # Assert that hosts in group were updated and events were produced
    assert len(mock_event_producer.write_event.call_args_list) == 3
    for call_arg in [json.loads(arg[0][0]) for arg in mock_event_producer.write_event.call_args_list]:
        # Make sure the group name and ID were updated on each host
        assert call_arg["type"] == "updated"
        assert call_arg["host"]["id"] in host_id_list
        assert call_arg["host"]["groups"][0]["name"] == new_name
        assert call_arg["host"]["groups"][0]["id"] == workspace_id


def test_workspace_mq_update_after_delete(mocker, flask_app, caplog):
    """An update message for a workspace that was already deleted is logged as a warning and skipped."""

    mocker.patch("app.queue.host_mq.group_repository.get_group_by_id_from_db", return_value=None)
    mock_patch_group = mocker.patch("app.queue.host_mq.group_repository.patch_group")

    workspace_id = str(generate_uuid())
    message = generate_kessel_workspace_message("update", workspace_id, "deleted-workspace")
    consumer = WorkspaceMessageConsumer(mocker.Mock(), flask_app, mocker.Mock(), mocker.Mock())

    with caplog.at_level(logging.WARNING):
        result = consumer.handle_message(json.dumps(message))

    assert result is None
    assert f"Group with ID {workspace_id} not found for update" in caplog.text
    mock_patch_group.assert_not_called()


@pytest.mark.usefixtures("flask_app")
def test_write_add_update_event_message(mocker):
    # Setup
    mock_event_producer = mocker.Mock()
    mock_notification_event_producer = mocker.Mock()
    mock_success_logger = mocker.Mock()
    mocker.patch("app.queue.host_mq.PayloadTrackerProcessingContext")
    mocker.patch("app.queue.host_mq.get_payload_tracker", return_value=mocker.Mock())
    mocker.patch(
        "app.serialization.get_staleness_timestamps",
        return_value={
            "stale_timestamp": datetime.now(),
            "stale_warning_timestamp": datetime.now(),
            "culled_timestamp": datetime.now(),
        },
    )
    mock_set_cached_system = mocker.patch("app.queue.host_mq.set_cached_system")
    mock_host_exists = mocker.patch("app.queue.host_mq.host_exists", return_value=True)
    mocker.patch("app.queue.host_mq.insights_id_owner_has_multiple_hosts", return_value=False)

    serialized_group = {
        "id": str(generate_uuid()),
        "name": "group-name",
        "ungrouped": True,
        "org_id": "org-id",
        "account": "account",
        "host_count": 1,
        "created": datetime.now().isoformat(),
        "updated": datetime.now().isoformat(),
    }

    # Mock normalized system profile
    class FakeColumn:
        def __init__(self, name):
            self.name = name

    class FakeTable:
        columns = [
            FakeColumn("org_id"),
            FakeColumn("host_id"),
            FakeColumn("owner_id"),
            FakeColumn("host_type"),
            FakeColumn("operating_system"),
            FakeColumn("bootc_status"),
        ]

    class FakeStaticProfile:
        __table__ = FakeTable()
        org_id = "org-id"
        host_id = "host-id"
        owner_id = "owner-id"
        host_type = None
        operating_system = None
        bootc_status = None

    class FakeHostRow:
        id = "host-id"
        org_id = "org-id"
        account = "acct"
        canonical_facts = {"insights_id": str(generate_uuid())}  # this line will be removed
        insights_id = generate_uuid()
        subscription_manager_id = generate_uuid()
        reporter = "puptoo"
        system_profile_facts = {"owner_id": "owner-id"}  # Legacy JSONB (still written for compatibility)
        groups = [serialized_group]
        host_type = None
        display_name = "test-display-name"
        ansible_host = "test-ansible-host"
        facts = {"namespace": []}
        tags = []
        per_reporter_staleness = {}
        created_on = datetime.now()
        modified_on = datetime.now()
        last_check_in = datetime.now()
        openshift_cluster_id = str(generate_uuid())
        static_system_profile = FakeStaticProfile()
        dynamic_system_profile = None

    result = OperationResult(
        row=FakeHostRow(),
        pm={"request_id": "abc"},
        so=None,
        et=EventType.created,
        sl=mock_success_logger,
    )

    # Act
    write_add_update_event_message(mock_event_producer, mock_notification_event_producer, result)

    # Assert that the event message contains only the limited group fields

    event_groups = json.loads(mock_event_producer.write_event.call_args[0][0])["host"]["groups"]
    assert event_groups == [{"name": "group-name", "id": serialized_group["id"], "ungrouped": True}]

    # Assert that all group fields were present when calling mock_set_cached_system
    cached_group = mock_set_cached_system.call_args[0][1]["groups"][0]
    assert cached_group == serialized_group
    mock_host_exists.assert_called_once_with("host-id", org_id="org-id", session=db.session)

    # Assert synchronous flush per ADR-0002
    assert mock_event_producer.write_event.call_args.kwargs["wait"] is True


@pytest.mark.usefixtures("flask_app")
def test_write_add_update_event_message_skips_deleted_host(mocker):
    mock_event_producer = mocker.Mock()
    mock_notification_event_producer = mocker.Mock()
    mock_success_logger = mocker.Mock()
    mocker.patch("app.queue.host_mq.PayloadTrackerProcessingContext")
    mocker.patch("app.queue.host_mq.get_payload_tracker", return_value=mocker.Mock())
    mocker.patch(
        "app.queue.host_mq.serialize_host",
        return_value={"id": "host-id", "org_id": "org-id", "reporter": "puptoo"},
    )
    mocker.patch("app.queue.host_mq.build_event_and_headers", return_value=("event", {}))
    mock_send_notification = mocker.patch("app.queue.host_mq.send_notification")
    mock_set_cached_system = mocker.patch("app.queue.host_mq.set_cached_system")
    mocker.patch("app.queue.host_mq.host_exists", return_value=False)

    host_row = mocker.Mock()
    host_row.id = generate_uuid()
    host_row.org_id = "org-id"
    host_row.account = "acct"
    host_row.insights_id = generate_uuid()

    result = OperationResult(
        row=host_row,
        pm={"request_id": "abc"},
        so=None,
        et=EventType.created,
        sl=mock_success_logger,
    )

    write_add_update_event_message(mock_event_producer, mock_notification_event_producer, result)

    mock_event_producer.write_event.assert_not_called()
    mock_send_notification.assert_not_called()
    mock_success_logger.assert_not_called()
    mock_set_cached_system.assert_not_called()


@pytest.mark.usefixtures("event_datetime_mock")
@pytest.mark.parametrize("reporter", ["rhsm-conduit", "rhsm-system-profile-bridge"])
def test_rhsm_with_containers_updates_normally(reporter, mq_create_or_update_host, db_get_host):
    """RHSM reporter sending containers should update them normally."""
    expected_insights_id = generate_uuid()
    initial_sp = {
        "workloads": {
            "ansible": {
                "controller_version": "1.0",
                "containers": [{"name": "receptor", "image": "quay.io/ansible/receptor:latest", "state": "running"}],
            }
        }
    }
    existing_host = create_reference_host_in_db(expected_insights_id, "puptoo", initial_sp)

    new_containers = [{"name": "receptor", "image": "quay.io/ansible/receptor:2.0", "state": "stopped"}]
    update_sp = {"workloads": {"ansible": {"controller_version": "2.0", "containers": new_containers}}}
    host = minimal_host(
        org_id=SYSTEM_IDENTITY["org_id"],
        insights_id=expected_insights_id,
        reporter=reporter,
        system_profile=update_sp,
    )
    mq_create_or_update_host(host)

    returned_host = db_get_host(existing_host.id)
    workloads = returned_host.dynamic_system_profile.workloads
    assert workloads["ansible"]["controller_version"] == "2.0"
    assert workloads["ansible"]["containers"] == new_containers

"""Group mutations preserve host data and emit complete inventory update events."""

import json
from copy import deepcopy
from datetime import UTC
from datetime import datetime
from datetime import timedelta

import pytest
from dateutil.parser import isoparse

from api.staleness_query import get_staleness_obj
from app.auth.identity import Identity
from app.auth.identity import to_auth_header
from app.culling import CONVENTIONAL_TIME_TO_DELETE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_SECONDS
from app.culling import CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS
from app.serialization import serialize_host
from tests.helpers.db_utils import db_host
from tests.helpers.test_utils import USER_IDENTITY


@pytest.fixture
def group_host(db_create_host):
    index = 0

    def create():
        nonlocal index
        index += 1
        profile = (
            {
                "host_type": "edge",
                "operating_system": {"name": "RHEL", "major": 9, "minor": 4},
                "bootc_status": {"booted": {"image_digest": "sha256:abc"}},
            }
            if index % 2
            else {}
        )
        return db_create_host(
            host=db_host(
                display_name=f"group-event-host-{index}",
                fqdn=f"group-event-host-{index}.example.test",
                system_profile_facts=profile,
            )
        )

    return create


@pytest.fixture
def populated_group(db_create_group, db_create_host_group_assoc, group_host):
    def create(name, count):
        group = db_create_group(name)
        hosts = [group_host() for _ in range(count)]
        for host in hosts:
            db_create_host_group_assoc(host.id, group.id)
        return group, hosts

    return create


@pytest.fixture
def ungrouped_group(db_create_group):
    return db_create_group("Ungrouped Hosts", ungrouped=True)


@pytest.fixture
def group_event_calls(event_producer, mocker):
    # Exercise real serialization and header encoding, stopping at the mocked Kafka client.
    mocker.patch("app.queue.events.hostname", return_value="host-inventory-unit")
    return event_producer._kafka_producer.produce


@pytest.fixture
def snapshot_group_hosts(db_get_host):
    def snapshot(hosts):
        # Capture before the request: a post-mutation serialization would hide preservation bugs.
        snapshots = {
            str(host.id): deepcopy(serialize_host(db_get_host(host.id), get_staleness_obj(host.org_id)))
            for host in hosts
        }
        for host in snapshots.values():
            # The API workspace alias is not part of the inventory Kafka host schema.
            host.pop("workspace")
        return snapshots

    return snapshot


def _mq_group(group, name=None):
    return {"id": str(group.id), "name": name or group.name, "ungrouped": group.ungrouped}


def _assert_group_updates(calls, before, groups_by_host, started, db_get_host, request_id=None):
    finished = datetime.now(UTC)
    assert len(calls.call_args_list) == len(before)
    seen = set()
    for call in calls.call_args_list:
        record = call.kwargs
        event = json.loads(record["value"])
        assert set(event) == {"timestamp", "type", "host", "metadata", "platform_metadata"}
        assert event["type"] == "updated"
        assert started <= isoparse(event["timestamp"]) <= finished
        assert event["metadata"] == {"request_id": request_id}
        assert event["platform_metadata"] == {"b64_identity": to_auth_header(Identity(USER_IDENTITY))}

        host = event["host"]
        host_id = host["id"]
        assert host_id in before
        assert host_id not in seen
        seen.add(host_id)
        assert record["key"] == host_id.encode()
        assert isoparse(host["updated"]) > isoparse(before[host_id]["updated"])
        assert isoparse(host["updated"]) == db_get_host(host_id).modified_on
        expected = {**before[host_id], "groups": groups_by_host[host_id], "updated": host["updated"]}
        assert host == expected

        check_in = isoparse(before[host_id]["last_check_in"])
        for field, seconds in (
            ("stale_timestamp", CONVENTIONAL_TIME_TO_STALE_SECONDS),
            ("stale_warning_timestamp", CONVENTIONAL_TIME_TO_STALE_WARNING_SECONDS),
            ("culled_timestamp", CONVENTIONAL_TIME_TO_DELETE_SECONDS),
        ):
            assert isoparse(host[field]) == check_in + timedelta(seconds=seconds)

        profile = before[host_id]["system_profile"]
        assert len(record["headers"]) == 8
        assert dict(record["headers"]) == {
            "event_type": b"updated",
            "request_id": (request_id or "").encode(),
            "producer": b"host-inventory-unit",
            "insights_id": (before[host_id]["insights_id"] or "").encode(),
            "reporter": before[host_id]["reporter"].encode(),
            # Conventional is the default header even though MQ omits it from system_profile.
            "host_type": profile.get("host_type", "conventional").encode(),
            "os_name": profile.get("operating_system", {}).get("name", "").encode(),
            "is_bootc": str(profile.get("bootc_status", {}).get("booted") is not None).encode(),
        }
    assert seen == set(before)


@pytest.mark.parametrize("host_count", [1, 3])
def test_create_group_events(
    host_count, group_host, snapshot_group_hosts, group_event_calls, api_create_group, db_get_host
):
    hosts = [group_host() for _ in range(host_count)]
    before = snapshot_group_hosts(hosts)
    started = datetime.now(UTC)
    status, group = api_create_group({"name": "Created group", "host_ids": list(before)})
    assert status == 201
    expected_group = {"id": group["id"], "name": "Created group", "ungrouped": False}
    _assert_group_updates(group_event_calls, before, dict.fromkeys(before, [expected_group]), started, db_get_host)


def test_patch_group_add_hosts_events(
    populated_group, group_host, snapshot_group_hosts, group_event_calls, api_patch_group, db_get_host
):
    group, members = populated_group("Additive patch", 2)
    new_host = group_host()
    before = snapshot_group_hosts([*members, new_host])
    expected_group = _mq_group(group)
    started = datetime.now(UTC)
    status, _ = api_patch_group(group.id, {"host_ids": list(before)})
    assert status == 200
    _assert_group_updates(group_event_calls, before, dict.fromkeys(before, [expected_group]), started, db_get_host)


@pytest.mark.parametrize("retained_count,rename", [(2, False), (0, False), (0, True)])
def test_patch_group_remove_hosts_events(
    retained_count,
    rename,
    populated_group,
    ungrouped_group,
    snapshot_group_hosts,
    group_event_calls,
    api_patch_group,
    db_get_host,
):
    group, members = populated_group("Removal patch", 3)
    before = snapshot_group_hosts(members)
    retained = list(before)[:retained_count]
    patch = {"host_ids": retained}
    if rename:
        patch["name"] = "Renamed empty group"
    groups = {host_id: [_mq_group(group) if host_id in retained else _mq_group(ungrouped_group)] for host_id in before}
    started = datetime.now(UTC)
    status, response = api_patch_group(group.id, patch)
    assert status == 200
    assert response["name"] == patch.get("name", "Removal patch")
    _assert_group_updates(group_event_calls, before, groups, started, db_get_host)


@pytest.mark.parametrize("rename", [False, True])
def test_patch_group_overlap_events(
    rename,
    populated_group,
    group_host,
    ungrouped_group,
    snapshot_group_hosts,
    group_event_calls,
    api_patch_group,
    db_get_host,
):
    group, members = populated_group("Overlapping patch", 2)
    new_host = group_host()
    before = snapshot_group_hosts([*members, new_host])
    requested = [str(members[1].id), str(new_host.id)]
    patch = {"host_ids": requested}
    name = "Renamed overlapping group" if rename else "Overlapping patch"
    if rename:
        patch["name"] = name
    groups = {
        host_id: [_mq_group(group, name) if host_id in requested else _mq_group(ungrouped_group)] for host_id in before
    }
    started = datetime.now(UTC)
    status, _ = api_patch_group(group.id, patch)
    assert status == 200
    _assert_group_updates(group_event_calls, before, groups, started, db_get_host)


def test_patch_group_replace_hosts_events(
    populated_group,
    group_host,
    ungrouped_group,
    snapshot_group_hosts,
    group_event_calls,
    api_patch_group,
    db_get_host,
):
    group, old_members = populated_group("Disjoint patch", 2)
    new_members = [group_host(), group_host()]
    requested = [str(host.id) for host in new_members]
    before = snapshot_group_hosts([*old_members, *new_members])
    groups = {
        host_id: [_mq_group(group) if host_id in requested else _mq_group(ungrouped_group)] for host_id in before
    }
    started = datetime.now(UTC)
    status, _ = api_patch_group(group.id, {"host_ids": requested})
    assert status == 200
    _assert_group_updates(group_event_calls, before, groups, started, db_get_host)


@pytest.mark.parametrize("host_count", [1, 3])
def test_patch_group_name_only_events(
    host_count, populated_group, snapshot_group_hosts, group_event_calls, api_patch_group, db_get_host
):
    group, members = populated_group("Original name", host_count)
    before = snapshot_group_hosts(members)
    expected_group = _mq_group(group, "New name")
    started = datetime.now(UTC)
    status, _ = api_patch_group(group.id, {"name": "New name"})
    assert status == 200
    _assert_group_updates(group_event_calls, before, dict.fromkeys(before, [expected_group]), started, db_get_host)


def test_patch_group_move_hosts_events(
    populated_group,
    group_host,
    ungrouped_group,
    snapshot_group_hosts,
    group_event_calls,
    api_patch_group,
    db_get_hosts_for_group,
    db_get_group_by_id,
    db_get_host,
):
    source, moved = populated_group("Source", 1)
    target, members = populated_group("Target", 2)
    source_id, target_id = source.id, target.id
    added = group_host()
    requested = [str(members[1].id), str(added.id), str(moved[0].id)]
    before = snapshot_group_hosts([*members, added, *moved])
    groups = {
        host_id: [_mq_group(target) if host_id in requested else _mq_group(ungrouped_group)] for host_id in before
    }
    started = datetime.now(UTC)
    status, _ = api_patch_group(target_id, {"host_ids": requested})
    assert status == 200
    assert db_get_hosts_for_group(source_id) == []
    assert {str(host.id) for host in db_get_hosts_for_group(target_id)} == set(requested)
    assert db_get_group_by_id(source_id).name == "Source"
    assert db_get_group_by_id(target_id).name == "Target"
    _assert_group_updates(group_event_calls, before, groups, started, db_get_host)


def test_delete_single_group_events(
    populated_group,
    ungrouped_group,
    snapshot_group_hosts,
    group_event_calls,
    api_delete_groups,
    db_get_group_by_id,
    db_get_host,
):
    group, members = populated_group("Deleted group", 3)
    group_id = group.id
    before = snapshot_group_hosts(members)
    expected_group = _mq_group(ungrouped_group)
    started = datetime.now(UTC)
    status, _ = api_delete_groups([group_id])
    assert status == 204
    assert db_get_group_by_id(group_id) is None
    _assert_group_updates(group_event_calls, before, dict.fromkeys(before, [expected_group]), started, db_get_host)


@pytest.mark.parametrize("second_host_count", [0, 2])
def test_delete_multiple_groups_events(
    second_host_count,
    populated_group,
    ungrouped_group,
    snapshot_group_hosts,
    group_event_calls,
    api_delete_groups,
    db_get_group_by_id,
    db_get_host,
):
    first, first_members = populated_group("First deleted group", 2)
    second, second_members = populated_group("Second deleted group", second_host_count)
    group_ids = [first.id, second.id]
    before = snapshot_group_hosts([*first_members, *second_members])
    expected_group = _mq_group(ungrouped_group)
    started = datetime.now(UTC)
    status, _ = api_delete_groups(group_ids)
    assert status == 204
    assert all(db_get_group_by_id(group_id) is None for group_id in group_ids)
    _assert_group_updates(group_event_calls, before, dict.fromkeys(before, [expected_group]), started, db_get_host)


@pytest.mark.parametrize("host_count", [1, 3])
def test_remove_group_hosts_events(
    host_count,
    populated_group,
    ungrouped_group,
    snapshot_group_hosts,
    group_event_calls,
    api_remove_hosts_from_group,
    db_get_hosts_for_group,
    db_get_host,
):
    group, members = populated_group("Remove members", 3)
    group_id = group.id
    remaining_ids = {str(host.id) for host in members[host_count:]}
    before = snapshot_group_hosts(members[:host_count])
    expected_group = _mq_group(ungrouped_group)
    started = datetime.now(UTC)
    status, _ = api_remove_hosts_from_group(group_id, list(before))
    assert status == 204
    assert {str(host.id) for host in db_get_hosts_for_group(group_id)} == remaining_ids
    _assert_group_updates(group_event_calls, before, dict.fromkeys(before, [expected_group]), started, db_get_host)


@pytest.mark.parametrize("host_count", [1, 3])
def test_add_group_hosts_events(
    host_count,
    populated_group,
    group_host,
    snapshot_group_hosts,
    group_event_calls,
    api_add_hosts_to_group,
    db_get_hosts_for_group,
    db_get_host,
):
    group, original_members = populated_group("Add members", 1)
    group_id = group.id
    new_members = [group_host() for _ in range(host_count)]
    before = snapshot_group_hosts(new_members)
    all_ids = {str(host.id) for host in [*original_members, *new_members]}
    expected_group = _mq_group(group)
    started = datetime.now(UTC)
    status, _ = api_add_hosts_to_group(group_id, list(before))
    assert status == 200
    assert {str(host.id) for host in db_get_hosts_for_group(group_id)} == all_ids
    _assert_group_updates(group_event_calls, before, dict.fromkeys(before, [expected_group]), started, db_get_host)


@pytest.mark.parametrize("host_count", [1, 3])
def test_remove_hosts_from_multiple_groups_events(
    host_count,
    populated_group,
    ungrouped_group,
    snapshot_group_hosts,
    group_event_calls,
    api_remove_hosts_from_diff_groups,
    db_get_hosts_for_group,
    db_get_host,
):
    first, first_members = populated_group("First source", 2)
    first_id = first.id
    second_members = []
    if host_count == 3:
        second, second_members = populated_group("Second source", 2)
        second_id = second.id
    removed = [*first_members, second_members[0]] if second_members else first_members[:1]
    before = snapshot_group_hosts(removed)
    first_remaining = {str(host.id) for host in first_members if str(host.id) not in before}
    second_remaining = {str(host.id) for host in second_members[1:]}
    expected_group = _mq_group(ungrouped_group)
    started = datetime.now(UTC)
    status, _ = api_remove_hosts_from_diff_groups(list(before))
    assert status == 204
    assert {str(host.id) for host in db_get_hosts_for_group(first_id)} == first_remaining
    if second_members:
        assert {str(host.id) for host in db_get_hosts_for_group(second_id)} == second_remaining
    _assert_group_updates(group_event_calls, before, dict.fromkeys(before, [expected_group]), started, db_get_host)


@pytest.mark.parametrize("host_count", [1, 3])
@pytest.mark.parametrize("request_id", ["a446557c-12ac-43d4-9ff9-a66dc0f0323c", "", None])
def test_group_events_preserve_request_id(
    host_count,
    request_id,
    populated_group,
    group_host,
    snapshot_group_hosts,
    group_event_calls,
    api_add_hosts_to_group,
    db_get_host,
):
    group, _ = populated_group("Request ID group", 0)
    before = snapshot_group_hosts([group_host() for _ in range(host_count)])
    expected_group = _mq_group(group)
    headers = {} if request_id is None else {"x-rh-insights-request-id": request_id}
    started = datetime.now(UTC)
    status, _ = api_add_hosts_to_group(group.id, list(before), extra_headers=headers)
    assert status == 200
    _assert_group_updates(
        group_event_calls, before, dict.fromkeys(before, [expected_group]), started, db_get_host, request_id
    )

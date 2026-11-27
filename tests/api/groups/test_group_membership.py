"""Membership boundary inputs and atomic rejection, sharing DB setup within probes."""

import pytest

from tests.helpers.api_utils import GROUP_URL
from tests.helpers.api_utils import HOST_URL
from tests.helpers.api_utils import build_groups_url
from tests.helpers.api_utils import get_required_headers
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import generate_uuid

UUID = "f8c1684c-aae7-4463-8cf4-773cc668862c"
# Path arguments are serialized to text, not sent as JSON. Compact UUIDs pass
# the character pattern but fail the UUID format check; uppercase is valid.
MALFORMED_UUIDS: tuple[tuple[object, str], ...] = (
    ([], "match"),
    ({}, "match"),
    ([UUID], "match"),
    (UUID.replace("-", "_"), "match"),
    (UUID.replace("-", "."), "match"),
    (UUID.replace("-", " "), "match"),
    (UUID.replace("-", ""), "uuid"),
    (UUID[:23], "match"),
    (UUID[:35], "match"),
    (UUID + "a", "match"),
    (UUID.replace("aa", "aá"), "match"),
    (UUID.replace("aa", "a$"), "match"),
    ("f8c1684c-aae7-4463-8cf4-773cc6-68862", "match"),
    (UUID[:10], "match"),
)
BAD_SERIALIZED_IDS: tuple[object, ...] = ([], {}, 1, 1.5, UUID + "a", "z" * 36, True, False, "None")


@pytest.fixture
def assert_membership(api_get, db_get_hosts_for_group):
    def check(group_id, name, host_ids):
        status, data = api_get(build_groups_url(str(group_id)))
        assert status == 200
        assert len(data["results"]) == 1
        group = data["results"][0]
        assert group["id"] == str(group_id)
        assert group["name"] == name
        assert group["host_count"] == len(host_ids)
        assert group["org_id"] == USER_IDENTITY["org_id"]
        assert {str(host.id) for host in db_get_hosts_for_group(group_id)} == set(host_ids)

    return check


@pytest.fixture
def populated_group(db_create_group_with_hosts, db_get_hosts_for_group):
    group_id = str(db_create_group_with_hosts("original name", 3).id)
    return group_id, {str(host.id) for host in db_get_hosts_for_group(group_id)}


def assert_invalid_uuid(status, data, value, reason="match"):
    assert status == 400
    assert ("''" if value == "" else str(value)) in data["detail"]
    assert reason in data["detail"]


@pytest.mark.usefixtures("event_producer")
def test_redundant_membership_additions(populated_group, api_add_hosts_to_group, assert_membership, subtests):
    group_id, host_ids = populated_group
    for requested in [sorted(host_ids)[:1], sorted(host_ids)]:
        with subtests.test(requested=requested):
            status, data = api_add_hosts_to_group(group_id, requested)
            assert status == 200
            assert data["id"] == group_id
            assert data["name"] == "original name"
            assert data["host_count"] == 3
            assert_membership(group_id, "original name", host_ids)


@pytest.mark.parametrize("move_count", [1, 3])
@pytest.mark.usefixtures("event_producer")
def test_move_members_to_empty_group(
    populated_group, db_create_group, api_add_hosts_to_group, assert_membership, move_count
):
    source_id, source_hosts = populated_group
    target_id = str(db_create_group("destination").id)
    moved_ids = set(sorted(source_hosts)[:move_count])
    status, data = api_add_hosts_to_group(target_id, sorted(moved_ids))
    assert status == 200
    assert data["id"] == target_id
    assert data["name"] == "destination"
    assert data["host_count"] == move_count
    assert_membership(source_id, "original name", source_hosts - moved_ids)
    assert_membership(target_id, "destination", moved_ids)


@pytest.mark.usefixtures("event_producer")
def test_move_members_and_new_hosts_to_empty_group(
    populated_group, db_create_group, db_create_host, api_add_hosts_to_group, assert_membership
):
    source_id, source_hosts = populated_group
    target_id = str(db_create_group("destination").id)
    new_ids = [str(db_create_host().id) for _ in range(2)]
    moved_id = sorted(source_hosts)[1]
    requested = [new_ids[0], moved_id, new_ids[1]]
    status, _ = api_add_hosts_to_group(target_id, requested)
    assert status == 200
    assert_membership(source_id, "original name", source_hosts - {moved_id})
    assert_membership(target_id, "destination", requested)


@pytest.mark.parametrize("member_count", [0, 3])
def test_rejected_empty_and_missing_host_additions(
    db_create_group_with_hosts,
    db_get_hosts_for_group,
    api_add_hosts_to_group,
    assert_membership,
    event_producer,
    mocker,
    subtests,
    member_count,
):
    group_id = str(db_create_group_with_hosts("original name", member_count).id)
    original_ids = {str(host.id) for host in db_get_hosts_for_group(group_id)}
    missing_id = generate_uuid()
    write_event = mocker.patch.object(event_producer, "write_event")
    for body, reason in [([], "empty array"), ([missing_id], missing_id)]:
        with subtests.test(body=body):
            status, data = api_add_hosts_to_group(group_id, body)
            assert status == 400
            assert reason in data["detail"]
            if body:
                assert "find existing host" in data["detail"]
            assert_membership(group_id, "original name", original_ids)
            write_event.assert_not_called()


def test_rejected_membership_body_types(
    populated_group,
    db_create_host,
    api_add_hosts_to_group,
    assert_membership,
    event_producer,
    mocker,
    subtests,
):
    group_id, original_ids = populated_group
    new_ids = [str(db_create_host().id) for _ in range(2)]
    cases = [
        (UUID, UUID, "array"),
        (123, "123", "array"),
        (False, "False", "array"),
        ([[UUID]], UUID, "string"),
        ([None], "None", "string"),
        ([123], "123", "string"),
        ([False], "False", "string"),
        ([UUID[:35]], UUID[:35], "match"),
        ([UUID + "a"], UUID + "a", "match"),
        ([UUID.replace("-", "_")], UUID.replace("-", "_"), "match"),
        ([UUID.replace("-", "")], UUID.replace("-", ""), "uuid"),
        (["z" * 36], "z" * 36, "match"),
        ({}, "{}", "array"),
        ({"host_ids": new_ids}, "host_ids", "array"),
    ]
    cases.extend(
        ({field: "replacement"}, field, "array")
        for field in ("id", "account", "created_on", "modified_on", "name", "unknown")
    )
    write_event = mocker.patch.object(event_producer, "write_event")
    for body, offending, reason in cases:
        with subtests.test(body=body):
            status, data = api_add_hosts_to_group(group_id, body)
            assert status == 400
            assert offending in data["detail"]
            assert reason in data["detail"]
            assert_membership(group_id, "original name", original_ids)
            write_event.assert_not_called()


def test_membership_post_without_body(
    populated_group, flask_client, assert_membership, event_producer, mocker, subtests
):
    group_id, original_ids = populated_group
    write_event = mocker.patch.object(event_producer, "write_event")
    # Unlike api_add_hosts_to_group(None), b"" is genuinely absent HTTP content.
    for content, reason in ((b"", "required"), (b"null", "null")):
        with subtests.test(content=content):
            response = flask_client.post(
                f"{GROUP_URL}/{group_id}/hosts", content=content, headers=get_required_headers(USER_IDENTITY)
            )
            assert response.status_code == 400
            assert reason in response.json()["detail"].lower()
            if content:
                assert "host_ids" in response.json()["detail"]
            assert_membership(group_id, "original name", original_ids)
            write_event.assert_not_called()


def test_mixed_valid_and_invalid_membership_additions(
    populated_group,
    db_create_host,
    api_add_hosts_to_group,
    assert_membership,
    event_producer,
    mocker,
    subtests,
):
    group_id, original_ids = populated_group
    new_ids = [str(db_create_host().id) for _ in range(2)]
    write_event = mocker.patch.object(event_producer, "write_event")
    for bad_id, reason in [(generate_uuid(), "find existing host"), (UUID[:10], "match")]:
        with subtests.test(bad_id=bad_id):
            status, data = api_add_hosts_to_group(group_id, [new_ids[0], bad_id, new_ids[1]])
            assert_invalid_uuid(status, data, bad_id, reason)
            assert_membership(group_id, "original name", original_ids)
            write_event.assert_not_called()


def test_duplicate_real_host_additions(
    db_create_group, db_create_host, api_add_hosts_to_group, assert_membership, event_producer, mocker, subtests
):
    group_id = str(db_create_group("original name").id)
    host_id = str(db_create_host().id)
    other_id = str(db_create_host().id)
    write_event = mocker.patch.object(event_producer, "write_event")
    for body in ([host_id, host_id], [other_id, host_id, host_id]):
        with subtests.test(body=body):
            status, data = api_add_hosts_to_group(group_id, body)
            assert status == 400
            assert "unique" in data["detail"].lower()
            assert_membership(group_id, "original name", set())
            write_event.assert_not_called()


def test_invalid_membership_group_paths(
    populated_group,
    db_create_group_with_hosts,
    db_get_hosts_for_group,
    api_add_hosts_to_group,
    api_remove_hosts_from_group,
    api_get,
    assert_membership,
    event_producer,
    mocker,
    subtests,
):
    group_id, original_ids = populated_group
    host_id = sorted(original_ids)[0]
    ungrouped_id = str(db_create_group_with_hosts("Ungrouped Hosts", 1, ungrouped=True).id)
    ungrouped_host_id = str(db_get_hosts_for_group(ungrouped_id)[0].id)
    expected_host_ids = original_ids | {ungrouped_host_id}
    status, before = api_get(GROUP_URL)
    assert status == 200
    status, hosts_before = api_get(HOST_URL)
    assert status == 200
    assert {host["id"] for host in hosts_before["results"]} == expected_host_ids
    write_event = mocker.patch.object(event_producer, "write_event")
    for bad_id, reason in MALFORMED_UUIDS:
        with subtests.test(bad_id=bad_id):
            status, data = api_add_hosts_to_group(bad_id, [ungrouped_host_id])
            assert_invalid_uuid(status, data, bad_id, reason)
            assert_membership(group_id, "original name", original_ids)
            assert_membership(ungrouped_id, "Ungrouped Hosts", {ungrouped_host_id})
            status, data = api_remove_hosts_from_group(bad_id, [host_id])
            assert_invalid_uuid(status, data, bad_id, reason)
            assert_membership(group_id, "original name", original_ids)
            status, after = api_get(GROUP_URL)
            assert status == 200
            assert after["total"] == before["total"]
            status, hosts_after = api_get(HOST_URL)
            assert status == 200
            assert hosts_after["total"] == hosts_before["total"]
            assert {host["id"] for host in hosts_after["results"]} == expected_host_ids
            write_event.assert_not_called()


def test_missing_membership_group_paths(
    populated_group,
    db_create_group_with_hosts,
    db_get_hosts_for_group,
    api_add_hosts_to_group,
    api_remove_hosts_from_group,
    api_delete_groups,
    api_get,
    assert_membership,
    event_producer,
    mocker,
    subtests,
):
    group_id, original_ids = populated_group
    host_id = sorted(original_ids)[0]
    ungrouped_id = str(db_create_group_with_hosts("Ungrouped Hosts", 1, ungrouped=True).id)
    ungrouped_host_id = str(db_get_hosts_for_group(ungrouped_id)[0].id)
    expected_host_ids = original_ids | {ungrouped_host_id}
    status, groups_before = api_get(GROUP_URL)
    assert status == 200
    status, hosts_before = api_get(HOST_URL)
    assert status == 200
    assert {host["id"] for host in hosts_before["results"]} == expected_host_ids
    write_event = mocker.patch.object(event_producer, "write_event")
    missing_id = generate_uuid()
    for path_id in (missing_id, missing_id.upper()):
        with subtests.test(path_id=path_id):
            status, data = api_add_hosts_to_group(path_id, [ungrouped_host_id])
            assert status == 404
            assert path_id.lower() in data["detail"].lower()
            assert_membership(ungrouped_id, "Ungrouped Hosts", {ungrouped_host_id})
            status, data = api_remove_hosts_from_group(path_id, [host_id])
            assert status == 404
            assert path_id.lower() in data["detail"].lower()
            status, _ = api_delete_groups([path_id])
            assert status == 404
            status, groups_after = api_get(GROUP_URL)
            assert status == 200
            assert groups_after["total"] == groups_before["total"]
            status, hosts_after = api_get(HOST_URL)
            assert status == 200
            assert hosts_after["total"] == hosts_before["total"]
            assert {host["id"] for host in hosts_after["results"]} == expected_host_ids
            assert_membership(group_id, "original name", original_ids)
            write_event.assert_not_called()


def test_rejected_group_deletion_ids(
    db_create_group_with_hosts,
    db_get_hosts_for_group,
    api_delete_groups,
    api_get,
    assert_membership,
    event_producer,
    mocker,
    subtests,
):
    group_ids = [str(db_create_group_with_hosts(f"original {index}", 1).id) for index in range(3)]
    original_members = {
        group_id: {str(host.id) for host in db_get_hosts_for_group(group_id)} for group_id in group_ids
    }
    status, before = api_get(GROUP_URL)
    assert status == 200
    write_event = mocker.patch.object(event_producer, "write_event")
    for bad_id in BAD_SERIALIZED_IDS:
        for requested in ([bad_id], [group_ids[0], bad_id, group_ids[2]]):
            with subtests.test(requested=requested):
                status, data = api_delete_groups(requested)
                assert_invalid_uuid(status, data, bad_id)
                status, after = api_get(GROUP_URL)
                assert status == 200
                assert after["total"] == before["total"]
                for index, group_id in enumerate(group_ids):
                    assert_membership(group_id, f"original {index}", original_members[group_id])
                write_event.assert_not_called()
    for bad_id in ("group", "78", "1.223434"):
        with subtests.test(bad_id=bad_id):
            status, data = api_delete_groups([bad_id, group_ids[0]])
            assert_invalid_uuid(status, data, bad_id)
            status, after = api_get(GROUP_URL)
            assert status == 200
            assert after["total"] == before["total"]
            for index, group_id in enumerate(group_ids):
                assert_membership(group_id, f"original {index}", original_members[group_id])
            write_event.assert_not_called()


def test_empty_delete_path_arguments(
    populated_group,
    api_delete_groups,
    api_remove_hosts_from_group,
    api_get,
    assert_membership,
    event_producer,
    mocker,
    subtests,
):
    group_id, original_ids = populated_group
    status, before = api_get(GROUP_URL)
    assert status == 200
    write_event = mocker.patch.object(event_producer, "write_event")
    for empty_argument in ([], {}, ""):
        with subtests.test(empty_argument=empty_argument):
            status, data = api_delete_groups(empty_argument)
            assert status == 405
            assert data["title"] == "Method Not Allowed"
            status, data = api_remove_hosts_from_group(group_id, empty_argument)
            assert status == 405
            assert data["title"] == "Method Not Allowed"
            status, after = api_get(GROUP_URL)
            assert status == 200
            assert after["total"] == before["total"]
            assert_membership(group_id, "original name", original_ids)
            write_event.assert_not_called()


def test_rejected_per_group_removal_host_ids(
    populated_group,
    api_remove_hosts_from_group,
    assert_membership,
    event_producer,
    mocker,
    subtests,
):
    group_id, original_ids = populated_group
    members = sorted(original_ids)
    write_event = mocker.patch.object(event_producer, "write_event")
    for bad_id, reason in (*MALFORMED_UUIDS, ("", "match")):
        with subtests.test(bad_id=bad_id):
            status, data = api_remove_hosts_from_group(group_id, [members[0], bad_id, members[2]])
            assert_invalid_uuid(status, data, bad_id, reason)
            assert_membership(group_id, "original name", original_ids)
            write_event.assert_not_called()


def test_missing_and_wrong_group_members(
    populated_group,
    db_create_group_with_hosts,
    db_get_hosts_for_group,
    api_remove_hosts_from_group,
    assert_membership,
    event_producer,
    mocker,
    subtests,
):
    group_id, original_ids = populated_group
    other_group_id = str(db_create_group_with_hosts("other group", 1).id)
    other_ids = {str(host.id) for host in db_get_hosts_for_group(other_group_id)}
    missing_id = generate_uuid()
    write_event = mocker.patch.object(event_producer, "write_event")
    for host_id in (missing_id, missing_id.upper(), *other_ids):
        with subtests.test(host_id=host_id):
            status, _ = api_remove_hosts_from_group(group_id, [host_id])
            assert status == 404
            assert_membership(group_id, "original name", original_ids)
            assert_membership(other_group_id, "other group", other_ids)
            write_event.assert_not_called()


def test_rejected_bulk_removal_host_ids(
    populated_group,
    api_remove_hosts_from_diff_groups,
    assert_membership,
    event_producer,
    mocker,
    subtests,
):
    group_id, original_ids = populated_group
    member_id = sorted(original_ids)[0]
    write_event = mocker.patch.object(event_producer, "write_event")
    for bad_id in BAD_SERIALIZED_IDS:
        for requested in ([bad_id], [member_id, bad_id]):
            with subtests.test(requested=requested):
                status, data = api_remove_hosts_from_diff_groups(requested)
                assert_invalid_uuid(status, data, bad_id)
                assert_membership(group_id, "original name", original_ids)
                write_event.assert_not_called()
    missing_id = generate_uuid()
    for requested in ([missing_id], [member_id, missing_id]):
        with subtests.test(requested=requested):
            status, data = api_remove_hosts_from_diff_groups(requested)
            assert status == 404
            assert "hosts not found" in data["detail"].lower()
            assert_membership(group_id, "original name", original_ids)
            write_event.assert_not_called()

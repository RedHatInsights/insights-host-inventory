import contextlib
import json
from unittest import mock

import pytest

from app.auth.identity import Identity
from app.auth.identity import to_auth_header
from tests.helpers.api_utils import GROUP_WRITE_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import create_mock_rbac_response
from tests.helpers.api_utils import mocked_post_workspace_not_found
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import generate_uuid


@pytest.mark.usefixtures("event_producer")
def test_delete_non_existent_group(api_delete_groups):
    group_id = generate_uuid()

    response_status, _ = api_delete_groups([group_id])

    assert_response_status(response_status, expected_status=404)


def test_delete_with_invalid_group_id(api_delete_groups):
    group_id = "notauuid"

    response_status, _ = api_delete_groups(group_id)

    assert_response_status(response_status, expected_status=400)


@pytest.mark.usefixtures("event_producer")
def test_delete_group_ids(db_create_group, db_get_group_by_id, api_delete_groups):
    group_id_list = [str(db_create_group(f"test_group{g_index}").id) for g_index in range(3)]

    response_status, _ = api_delete_groups(group_id_list)

    assert_response_status(response_status, expected_status=204)

    for group_id in group_id_list:
        assert not db_get_group_by_id(group_id)


def test_remove_hosts_from_nonexistent_group(db_create_host, api_remove_hosts_from_group, event_producer, mocker):
    mocker.patch.object(event_producer, "write_event")
    # Test against nonexistent group
    host_id = db_create_host().id
    response_status, _ = api_remove_hosts_from_group(generate_uuid(), [host_id])
    assert response_status == 404

    assert event_producer.write_event.call_count == 0


@pytest.mark.usefixtures("enable_rbac")
def test_remove_hosts_from_group_RBAC_denied(
    subtests, mocker, db_create_group, db_create_host, api_remove_hosts_from_group
):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    group_id = str(db_create_group("new_group").id)

    for response_file in GROUP_WRITE_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)

        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response
            host_id_list = [db_create_host().id for _ in range(3)]
            response_status, _ = api_remove_hosts_from_group(group_id, [str(host) for host in host_id_list[0:2]])

            assert_response_status(response_status, 403)


@pytest.mark.usefixtures("enable_rbac")
def test_remove_hosts_from_group_RBAC_denied_missing_group(
    subtests, mocker, db_create_host, api_remove_hosts_from_group
):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    group_id = str(generate_uuid())

    for response_file in GROUP_WRITE_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)

        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response
            host_id_list = [db_create_host().id for _ in range(3)]
            response_status, _ = api_remove_hosts_from_group(group_id, [str(host) for host in host_id_list[0:2]])

            assert_response_status(response_status, 404)


def test_remove_hosts_from_someone_elses_group(
    db_create_group,
    db_create_host,
    db_create_host_group_assoc,
    api_remove_hosts_from_group,
    db_get_hosts_for_group,
    event_producer,
    mocker,
):
    mocker.patch.object(event_producer, "write_event")
    # Test against group that has a different org ID
    diff_identity = {"org_id": "diff_org", "account_number": "diff_acct"}

    group_id = db_create_group("notyourgroup", diff_identity).id
    host_id = db_create_host(diff_identity).id
    db_create_host_group_assoc(host_id, group_id)

    response_status, _ = api_remove_hosts_from_group(group_id, [host_id])
    assert response_status == 404

    hosts_after = db_get_hosts_for_group(group_id)
    assert hosts_after[0].id == host_id

    # No hosts removed, so no messages should have been sent
    assert event_producer.write_event.call_count == 0


@pytest.mark.usefixtures("enable_rbac")
def test_delete_groups_RBAC_denied(subtests, mocker, db_create_group, api_delete_groups):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    group_id_list = [str(db_create_group(f"test_group{g_index}").id) for g_index in range(3)]

    for response_file in GROUP_WRITE_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)

        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            response_status, _ = api_delete_groups(group_id_list)

            assert_response_status(response_status, 403)


@pytest.mark.usefixtures("enable_rbac")
def test_delete_groups_RBAC_allowed_specific_groups(mocker, db_create_group, api_delete_groups):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    group_id_list = [str(db_create_group(f"test_group{g_index}").id) for g_index in range(3)]

    mock_rbac_response = create_mock_rbac_response(
        "tests/helpers/rbac-mock-data/inv-groups-write-resource-defs-template.json"
    )
    # Grant permissions to all 3 groups
    mock_rbac_response[0]["resourceDefinitions"][0]["attributeFilter"]["value"] = group_id_list

    get_rbac_permissions_mock.return_value = mock_rbac_response
    response_status, _ = api_delete_groups(group_id_list)

    # Should be allowed
    assert_response_status(response_status, 204)


@pytest.mark.usefixtures("enable_rbac")
def test_delete_groups_RBAC_denied_specific_groups(mocker, db_create_group, api_delete_groups):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    group_id_list = [str(db_create_group(f"test_group{g_index}").id) for g_index in range(3)]

    mock_rbac_response = create_mock_rbac_response(
        "tests/helpers/rbac-mock-data/inv-groups-write-resource-defs-template.json"
    )
    # Only grant permission to one group in the list
    mock_rbac_response[0]["resourceDefinitions"][0]["attributeFilter"]["value"] = [group_id_list[1]]

    get_rbac_permissions_mock.return_value = mock_rbac_response
    response_status, _ = api_delete_groups(group_id_list)

    # Should be denied because access is not granted to two of the groups
    assert_response_status(response_status, 403)


def test_delete_hosts_from_different_groups(
    db_create_group,
    db_create_host,
    db_get_hosts_for_group,
    db_create_host_group_assoc,
    api_remove_hosts_from_diff_groups,
    event_producer,
    mocker,
):
    mocker.patch.object(event_producer, "write_event")

    # Create 2 groups and 4 hosts
    group1_id = str(db_create_group("test_group1").id)
    group2_id = str(db_create_group("test_group2").id)

    host_id_list1 = [str(db_create_host().id) for _ in range(2)]
    host_id_list2 = [str(db_create_host().id) for _ in range(2)]

    # Add 2 hosts to each group
    for host_id in host_id_list1:
        db_create_host_group_assoc(host_id, group1_id)
    for host_id in host_id_list2:
        db_create_host_group_assoc(host_id, group2_id)

    # Confirm that the associations exist
    hosts_before1 = db_get_hosts_for_group(group1_id)
    assert len(hosts_before1) == 2
    hosts_before2 = db_get_hosts_for_group(group2_id)
    assert len(hosts_before2) == 2

    # Remove one host from each group
    hosts_to_delete = [host_id_list1[0], host_id_list2[0]]
    response_status, _ = api_remove_hosts_from_diff_groups(hosts_to_delete)
    assert_response_status(response_status, 204)

    # Confirm that the groups now only contain the last host
    hosts1_after = db_get_hosts_for_group(group1_id)
    assert len(hosts1_after) == 1
    assert str(hosts1_after[0].id) == host_id_list1[1]
    hosts2_after = db_get_hosts_for_group(group2_id)
    assert len(hosts2_after) == 1
    assert str(hosts2_after[0].id) == host_id_list2[1]

    assert event_producer.write_event.call_count == 2
    for call_arg in event_producer.write_event.call_args_list:
        host = json.loads(call_arg[0][0])["host"]
        assert host["id"] in hosts_to_delete
        assert host["groups"][0]["ungrouped"] is True


@pytest.mark.usefixtures("enable_rbac")
def test_delete_hosts_from_different_groups_RBAC_denied(
    db_create_group,
    db_create_host,
    db_get_hosts_for_group,
    db_create_host_group_assoc,
    api_remove_hosts_from_diff_groups,
    event_producer,
    mocker,
):
    mocker.patch.object(event_producer, "write_event")
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    # Create 2 groups and 4 hosts
    group1_id = str(db_create_group("test_group1").id)
    group2_id = str(db_create_group("test_group2").id)

    host_id_list1 = [str(db_create_host().id) for _ in range(2)]
    host_id_list2 = [str(db_create_host().id) for _ in range(2)]

    # Add 2 hosts to each group
    for host_id in host_id_list1:
        db_create_host_group_assoc(host_id, group1_id)
    for host_id in host_id_list2:
        db_create_host_group_assoc(host_id, group2_id)

    # Confirm that the associations exist
    hosts_before1 = db_get_hosts_for_group(group1_id)
    assert len(hosts_before1) == 2
    hosts_before2 = db_get_hosts_for_group(group2_id)
    assert len(hosts_before2) == 2

    mock_rbac_response = create_mock_rbac_response(
        "tests/helpers/rbac-mock-data/inv-groups-write-resource-defs-template.json"
    )

    # Only grant permission to one group
    mock_rbac_response[0]["resourceDefinitions"][0]["attributeFilter"]["value"] = [group1_id]
    get_rbac_permissions_mock.return_value = mock_rbac_response

    # Try to remove one host from each group
    hosts_to_delete = [host_id_list1[0], host_id_list2[0]]

    response_status, _ = api_remove_hosts_from_diff_groups(hosts_to_delete)
    assert_response_status(response_status, 403)

    # Check that the hosts weren't deleted
    hosts_after1 = db_get_hosts_for_group(group1_id)
    assert len(hosts_after1) == 2
    hosts_after2 = db_get_hosts_for_group(group2_id)
    assert len(hosts_after2) == 2

    # No messages should have been sent
    assert event_producer.write_event.call_count == 0


def test_delete_hosts_no_group(
    db_create_group,
    db_create_host,
    db_get_hosts_for_group,
    db_create_host_group_assoc,
    api_remove_hosts_from_diff_groups,
    event_producer,
    mocker,
):
    mocker.patch.object(event_producer, "write_event")

    group_id = str(db_create_group("test_group1").id)
    host_id_list = [str(db_create_host().id) for _ in range(2)]

    # Add one host to the group
    db_create_host_group_assoc(host_id_list[0], group_id)

    # Confirm that the associations exist
    hosts_before = db_get_hosts_for_group(group_id)
    assert len(hosts_before) == 1

    response_status, _ = api_remove_hosts_from_diff_groups(host_id_list)
    assert_response_status(response_status, 204)

    # Confirm that the host was removed from the group
    hosts1_after = db_get_hosts_for_group(group_id)
    assert len(hosts1_after) == 0

    assert event_producer.write_event.call_count == 1
    for call_arg in event_producer.write_event.call_args_list:
        host = json.loads(call_arg[0][0])["host"]
        assert host["id"] == host_id_list[0]
        assert host["groups"][0]["ungrouped"] is True


@pytest.mark.usefixtures("event_producer")
def test_delete_non_empty_group(api_delete_groups, db_create_group_with_hosts):
    group = db_create_group_with_hosts("non_empty_group", 3)

    response_status, _ = api_delete_groups([group.id])
    assert_response_status(response_status, expected_status=204)


@pytest.mark.usefixtures("event_producer_mock", "notification_event_producer_mock")
def test_attempt_delete_group_read_only(api_delete_groups, mocker):
    with mocker.patch("lib.middleware.get_flag_value", return_value=True):
        response_status, _ = api_delete_groups([generate_uuid()])
        assert_response_status(response_status, expected_status=503)


@pytest.mark.usefixtures("event_producer")
def test_delete_non_empty_group_workspace_enabled(api_delete_groups, db_create_group_with_hosts):
    group = db_create_group_with_hosts("non_empty_group", 3)

    response_status, rd = api_delete_groups([group.id])
    assert_response_status(response_status, expected_status=204)


@pytest.mark.usefixtures("event_producer")
def test_delete_empty_group_workspace_enabled(api_delete_groups, db_create_group):
    group_id = str(db_create_group("test_group").id)

    response_status, _ = api_delete_groups([group_id])
    assert_response_status(response_status, expected_status=204)


@pytest.mark.parametrize("num_hosts_to_remove", [1, 2, 3])
def test_remove_hosts_from_existing_group(
    num_hosts_to_remove,
    db_create_group,
    db_create_host,
    db_get_ungrouped_group,
    db_get_hosts_for_group,
    db_create_host_group_assoc,
    api_remove_hosts_from_group,
    event_producer,
    mocker,
):
    TOTAL_HOSTS_CREATED = 3
    mocker.patch.object(event_producer, "write_event")
    # Create a group and hosts
    group_id = db_create_group("test_group").id
    host_id_list = [str(db_create_host().id) for _ in range(TOTAL_HOSTS_CREATED)]

    # Add the hosts to the group
    for host_id in host_id_list:
        db_create_host_group_assoc(host_id, group_id)

    # Confirm that the association exists
    hosts_before = db_get_hosts_for_group(group_id)
    assert len(hosts_before) == TOTAL_HOSTS_CREATED

    # Remove the first two hosts from the group
    response_status, _ = api_remove_hosts_from_group(group_id, host_id_list[:num_hosts_to_remove])
    assert response_status == 204

    # Confirm that the hosts have been removed from the original group
    hosts_after = db_get_hosts_for_group(group_id)
    assert len(hosts_after) == TOTAL_HOSTS_CREATED - num_hosts_to_remove

    # Confirm that Ungrouped Hosts now contains the removed hosts
    ungrouped_id = db_get_ungrouped_group(USER_IDENTITY["org_id"]).id
    ungrouped_hosts = db_get_hosts_for_group(ungrouped_id)
    assert len(ungrouped_hosts) == num_hosts_to_remove

    # Make sure the events associating hosts to "Ungrouped Hosts" exist
    assert event_producer.write_event.call_count == num_hosts_to_remove
    for call_arg in event_producer.write_event.call_args_list:
        event = json.loads(call_arg[0][0])
        host = event["host"]
        assert host["id"] in host_id_list[:num_hosts_to_remove]
        assert len(host["groups"]) == 1
        assert host["groups"][0]["ungrouped"] is True
        assert event["platform_metadata"] == {"b64_identity": to_auth_header(Identity(obj=USER_IDENTITY))}


@pytest.mark.usefixtures("enable_rbac")
def test_delete_hosts_from_diff_groups_post_kessel_migration(
    mocker,
    api_remove_hosts_from_diff_groups,
    db_create_group_with_hosts,
    db_create_group,
    event_producer,
    db_get_hosts_for_group,
):
    mocker.patch.object(event_producer, "write_event")
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    mock_rbac_response = create_mock_rbac_response(
        "tests/helpers/rbac-mock-data/inv-groups-write-resource-defs-template.json"
    )
    get_rbac_permissions_mock.return_value = mock_rbac_response

    group1 = db_create_group_with_hosts("test_group1", 2)
    group2 = db_create_group_with_hosts("test_group2", 3)
    group3 = db_create_group_with_hosts("test_group3", 3)

    ungrouped_group_id = str(db_create_group("ungrouped", ungrouped=True).id)

    hosts_to_delete = [
        str(db_get_hosts_for_group(group1.id)[0].id),
        str(db_get_hosts_for_group(group2.id)[0].id),
        str(db_get_hosts_for_group(group3.id)[0].id),
    ]
    response_status, _ = api_remove_hosts_from_diff_groups(hosts_to_delete)

    assert_response_status(response_status, 204)
    assert event_producer.write_event.call_count == 3

    # Check that the removed hosts were assigned to the ungrouped group
    for host in db_get_hosts_for_group(ungrouped_group_id):
        assert str(host.id) in hosts_to_delete


@pytest.mark.usefixtures("enable_kessel")
def test_delete_ungrouped_group_post_kessel_migration(
    mocker,
    api_delete_groups,
    db_create_group,
    event_producer,
    db_get_group_by_id,
    subtests,
):
    mocker.patch.object(event_producer, "write_event")

    # Create an ungrouped group and a standard group
    ungrouped_group_id = str(db_create_group("ungrouped group", ungrouped=True).id)
    grouped_group_id = str(db_create_group("standard group", ungrouped=False).id)

    for ids_to_delete in [[ungrouped_group_id], [ungrouped_group_id, grouped_group_id]]:
        with subtests.test():
            response_status, _ = api_delete_groups(ids_to_delete)

            # Should return 400, since we can't delete the "ungrouped" group
            assert_response_status(response_status, 400)

            # Confirm that neither group was deleted
            assert db_get_group_by_id(ungrouped_group_id)
            assert db_get_group_by_id(grouped_group_id)


@pytest.mark.usefixtures("event_producer")
def test_delete_multiple_groups(db_create_group, db_create_group_with_hosts, api_delete_groups):
    non_empty_group = db_create_group_with_hosts("non_empty_group", 3)
    empty_group = db_create_group("empty_group")
    response_status, _ = api_delete_groups([non_empty_group.id, empty_group.id])
    assert_response_status(response_status, expected_status=204)


@pytest.mark.usefixtures("enable_kessel", "event_producer")
@mock.patch("requests.Session.delete", new=mocked_post_workspace_not_found)
def test_delete_nonexistent_group_kessel(api_delete_groups):
    # Mock the metrics context manager bc we don't care about it here
    with mock.patch("lib.middleware.outbound_http_response_time") as mock_metric:
        mock_metric.labels.return_value.time.return_value = contextlib.nullcontext()

        response_status, _ = api_delete_groups([generate_uuid()], abort_status=404)
        assert_response_status(response_status, expected_status=404)


@pytest.mark.usefixtures("event_producer")
@pytest.mark.usefixtures("enable_rbac")
@mock.patch("requests.Session.delete", new=mocked_post_workspace_not_found)
def test_delete_existing_group_missing_workspace(api_delete_groups_kessel, db_create_group, mocker):
    group_id = db_create_group("test group").id

    # Mock RBAC permissions to allow request
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    mock_rbac_response = create_mock_rbac_response(
        "tests/helpers/rbac-mock-data/inv-groups-write-resource-defs-template.json"
    )
    get_rbac_permissions_mock.return_value = mock_rbac_response

    # Mock the metrics context manager bc we don't care about it here
    with mock.patch("lib.middleware.outbound_http_response_time") as mock_metric:
        mock_metric.labels.return_value.time.return_value = contextlib.nullcontext()

        response_status, _ = api_delete_groups_kessel([group_id])
        assert_response_status(response_status, expected_status=204)


def test_delete_ungrouped_host_from_group(
    db_create_group_with_hosts, db_get_hosts_for_group, api_remove_hosts_from_diff_groups
):
    ungrouped_group = db_create_group_with_hosts("ungrouped", 1, ungrouped=True)
    host_id_to_delete = str(db_get_hosts_for_group(ungrouped_group.id)[0].id)

    response_status, response_data = api_remove_hosts_from_diff_groups([host_id_to_delete])

    assert_response_status(response_status, 400)


def test_delete_host_from_ungrouped_group(
    db_create_group_with_hosts, db_get_hosts_for_group, api_remove_hosts_from_group
):
    ungrouped_group = db_create_group_with_hosts("ungrouped", 1, ungrouped=True)
    host_id_to_delete = str(db_get_hosts_for_group(ungrouped_group.id)[0].id)

    response_status, response_data = api_remove_hosts_from_group(ungrouped_group.id, [host_id_to_delete])

    assert_response_status(response_status, 400)
    assert str(ungrouped_group.id) in response_data["detail"]


@pytest.mark.usefixtures("event_producer")
def test_delete_host_from_group_no_ungrouped(
    db_create_group_with_hosts, db_get_hosts_for_group, api_remove_hosts_from_group
):
    ungrouped_group = db_create_group_with_hosts("ungrouped", 1, ungrouped=False)
    host_id_to_delete = str(db_get_hosts_for_group(ungrouped_group.id)[0].id)

    response_status, _ = api_remove_hosts_from_group(ungrouped_group.id, [host_id_to_delete])

    assert_response_status(response_status, 204)


@pytest.mark.parametrize("ungrouped", [True, False])
@pytest.mark.usefixtures("event_producer")
def test_delete_host_from_nonexistent_group(
    ungrouped, db_create_group_with_hosts, db_get_hosts_for_group, api_remove_hosts_from_group
):
    group = db_create_group_with_hosts("test group", 1, ungrouped=ungrouped)
    host_id = str(db_get_hosts_for_group(group.id)[0].id)

    response_status, response_data = api_remove_hosts_from_group(str(generate_uuid()), [host_id])

    assert_response_status(response_status, 404)
    assert "Group not found" in response_data["detail"]

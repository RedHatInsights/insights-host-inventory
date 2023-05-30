import json

from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import create_mock_rbac_response
from tests.helpers.api_utils import WRITE_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.test_utils import generate_uuid


def test_delete_non_existent_group(api_delete_groups, event_producer):
    group_id = generate_uuid()

    response_status, response_data = api_delete_groups([group_id])

    assert_response_status(response_status, expected_status=404)


def test_delete_with_invalid_group_id(api_delete_groups):
    group_id = "notauuid"

    response_status, response_data = api_delete_groups(group_id)

    assert_response_status(response_status, expected_status=400)


def test_delete_group_ids(db_create_group, db_get_group_by_id, api_delete_groups, event_producer):
    group_id_list = [str(db_create_group(f"test_group{g_index}").id) for g_index in range(3)]

    response_status, response_data = api_delete_groups(group_id_list)

    assert_response_status(response_status, expected_status=204)

    for group_id in group_id_list:
        assert not db_get_group_by_id(group_id)


def test_remove_hosts_from_existing_group(
    db_create_group,
    db_create_host,
    db_get_hosts_for_group,
    db_create_host_group_assoc,
    api_remove_hosts_from_group,
    event_producer,
    mocker,
):
    mocker.patch.object(event_producer, "write_event")
    # Create a group and 3 hosts
    group_id = db_create_group("test_group").id
    host_id_list = [str(db_create_host().id) for _ in range(3)]

    # Add all 3 hosts to the group
    for host_id in host_id_list:
        db_create_host_group_assoc(host_id, group_id)

    # Confirm that the association exists
    hosts_before = db_get_hosts_for_group(group_id)
    assert len(hosts_before) == 3

    # Remove the first two hosts from the group
    response_status, _ = api_remove_hosts_from_group(group_id, [host for host in host_id_list[0:2]])
    assert response_status == 204

    # Confirm that the group now only contains the last host
    hosts_after = db_get_hosts_for_group(group_id)
    assert len(hosts_after) == 1
    assert str(hosts_after[0].id) == host_id_list[2]

    assert event_producer.write_event.call_count == 2
    for call_arg in event_producer.write_event.call_args_list:
        host = json.loads(call_arg[0][0])["host"]
        assert host["id"] in host_id_list[0:2]
        assert len(host["groups"]) == 0


def test_remove_hosts_from_nonexistent_group(db_create_host, api_remove_hosts_from_group, event_producer, mocker):
    mocker.patch.object(event_producer, "write_event")
    # Test against nonexistent group
    host_id = db_create_host().id
    response_status, _ = api_remove_hosts_from_group(generate_uuid(), [host_id])
    assert response_status == 404

    assert event_producer.write_event.call_count == 0


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


def test_delete_groups_RBAC_denied(subtests, mocker, db_create_group, api_delete_groups, enable_rbac):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    group_id_list = [str(db_create_group(f"test_group{g_index}").id) for g_index in range(3)]

    for response_file in WRITE_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)

        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            response_status, _ = api_delete_groups(group_id_list)

            assert_response_status(response_status, 403)


def test_delete_groups_RBAC_allowed_specific_groups(
    mocker, db_create_group, api_delete_groups, enable_rbac, event_producer
):
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


def test_delete_groups_RBAC_denied_specific_groups(mocker, db_create_group, api_delete_groups, enable_rbac):
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

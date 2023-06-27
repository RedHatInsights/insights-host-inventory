import uuid

from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import create_mock_rbac_response
from tests.helpers.api_utils import GROUP_WRITE_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.test_utils import generate_uuid


def test_add_host_to_group(
    db_create_group, db_create_host, db_get_hosts_for_group, api_add_hosts_to_group, event_producer
):
    # Create a group and 3 hosts
    group_id = db_create_group("test_group").id
    host_id_list = [db_create_host().id for _ in range(3)]

    response_status, _ = api_add_hosts_to_group(group_id, [str(host) for host in host_id_list[0:2]])
    assert response_status == 200

    # Confirm that the group now only contains  2 hosts
    hosts_after = db_get_hosts_for_group(group_id)
    assert len(hosts_after) == 2
    assert hosts_after[0].id in host_id_list
    assert hosts_after[1].id in host_id_list


def test_add_host_to_group_RBAC_denied(
    subtests, mocker, db_create_host, db_create_group_with_hosts, api_add_hosts_to_group, enable_rbac
):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    group_id = str(db_create_group_with_hosts("new_group", 3).id)

    for response_file in GROUP_WRITE_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)

        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response
            host_id_list = [db_create_host().id for _ in range(3)]
            response_status, _ = api_add_hosts_to_group(group_id, [str(host) for host in host_id_list[0:2]])

            assert_response_status(response_status, 403)


def test_add_host_to_group_RBAC_allowed_specific_groups(
    mocker,
    db_create_group_with_hosts,
    api_add_hosts_to_group,
    db_create_host,
    db_get_hosts_for_group,
    enable_rbac,
    event_producer,
):
    # Create a group and 3 hosts
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    group_id = str(db_create_group_with_hosts("new_group", 3).id)

    # Make a list of allowed group IDs (including some mock ones)
    group_id_list = [generate_uuid(), group_id, generate_uuid()]

    # Grant permissions to all 3 groups
    mock_rbac_response = create_mock_rbac_response(
        "tests/helpers/rbac-mock-data/inv-groups-write-resource-defs-template.json"
    )
    mock_rbac_response[0]["resourceDefinitions"][0]["attributeFilter"]["value"] = group_id_list
    get_rbac_permissions_mock.return_value = mock_rbac_response

    host_id_list = [db_create_host().id for _ in range(3)]

    response_status, _ = api_add_hosts_to_group(group_id, [str(host) for host in host_id_list[0:2]])

    # Should be allowed
    assert_response_status(response_status, 200)
    # Group should now have 5 hosts
    hosts_after = db_get_hosts_for_group(group_id)
    assert len(hosts_after) == 5


def test_add_host_to_group_RBAC_denied_specific_groups(
    mocker, db_create_group_with_hosts, api_add_hosts_to_group, db_create_host, enable_rbac
):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    group_id = str(db_create_group_with_hosts("new_group", 3).id)

    # Deny access to created group
    mock_rbac_response = create_mock_rbac_response(
        "tests/helpers/rbac-mock-data/inv-groups-write-resource-defs-template.json"
    )
    mock_rbac_response[0]["resourceDefinitions"][0]["attributeFilter"]["value"] = [generate_uuid(), generate_uuid()]
    get_rbac_permissions_mock.return_value = mock_rbac_response

    host_id_list = [db_create_host().id for _ in range(3)]

    response_status, _ = api_add_hosts_to_group(group_id, [str(host) for host in host_id_list[0:2]])

    # Access was not granted
    assert_response_status(response_status, 403)


def test_add_associated_host_to_same_group(
    db_create_group,
    db_create_host,
    db_get_hosts_for_group,
    db_create_host_group_assoc,
    api_add_hosts_to_group,
    event_producer,
    mocker,
):
    mocker.patch.object(event_producer, "write_event")

    # Create a group and 3 hosts
    group_id = db_create_group("test_group").id
    host_id_list = [db_create_host().id for _ in range(3)]

    # Add 1 host to the group
    db_create_host_group_assoc(host_id_list[1], group_id)

    # Confirm that the association exists
    hosts_before = db_get_hosts_for_group(group_id)
    assert len(hosts_before) == 1

    # Confirm that the API is allowed to add the hosts even though one is associated
    response_status, _ = api_add_hosts_to_group(group_id, [str(host) for host in host_id_list])
    assert response_status == 200

    # Confirm the host count afterwards
    assert len(db_get_hosts_for_group(group_id)) == 3

    # Make sure that the events were produced
    assert event_producer.write_event.call_count == 3


def test_add_associated_host_to_different_group(
    db_create_group,
    db_create_host,
    db_get_hosts_for_group,
    db_create_host_group_assoc,
    api_add_hosts_to_group,
    event_producer,
    mocker,
):
    mocker.patch.object(event_producer, "write_event")

    # Create a group and 3 hosts
    group1_id = db_create_group("test_group").id
    group2_id = db_create_group("test_group2").id
    host_id_list = [str(db_create_host().id) for _ in range(3)]

    # Add the second 2 hosts to a group
    db_create_host_group_assoc(host_id_list[1], group1_id)
    db_create_host_group_assoc(host_id_list[2], group2_id)

    # Confirm that the association exists
    hosts_before = db_get_hosts_for_group(group1_id)
    assert len(hosts_before) == 1
    hosts_before = db_get_hosts_for_group(group2_id)
    assert len(hosts_before) == 1

    # Confirm that the API does not allow these hosts to be added to the group
    response_status, _ = api_add_hosts_to_group(group1_id, host_id_list)
    assert response_status == 400

    # Make sure that everything was rolled back and no events were produced
    assert len(db_get_hosts_for_group(group1_id)) == 1
    assert event_producer.write_event.call_count == 0


def test_add_host_list_with_one_associated_host_to_group(
    db_create_group,
    db_create_host,
    db_get_hosts_for_group,
    db_create_host_group_assoc,
    api_add_hosts_to_group,
    event_producer,
):
    # Create a group and 3 hosts
    group_id = db_create_group("test_group").id
    host_id_list = [db_create_host().id for _ in range(3)]

    # Add first and last hosts to the group
    db_create_host_group_assoc(host_id_list[0], group_id)
    db_create_host_group_assoc(host_id_list[2], group_id)

    # adding only id[1], since 0 and 2 already associated above
    response_status, _ = api_add_hosts_to_group(group_id, [str(host) for host in host_id_list])
    assert response_status == 200

    # Confirm that the group now only contains  2 hosts
    hosts_after = db_get_hosts_for_group(group_id)
    assert len(hosts_after) == 3


def test_update_time_after_adding_host_to_group(
    db_create_group,
    db_create_host,
    api_add_hosts_to_group,
    event_producer,
):
    # Create a group and 3 hosts
    group = db_create_group("test_group")
    group_id = group.id
    host_id_list = [db_create_host().id for _ in range(3)]

    response_status, group = api_add_hosts_to_group(group_id, [str(host) for host in host_id_list])

    assert response_status == 200
    assert group["host_count"] == 3

    # add 4 host to the same group
    response_status, updated_group = api_add_hosts_to_group(group_id, [str(db_create_host().id)])
    assert response_status == 200
    assert updated_group["host_count"] == 4

    # compare the two update times
    from dateutil.parser import parse

    first_update = parse(group["updated"])
    second_update = parse(updated_group["updated"])
    assert second_update > first_update


def test_add_host_to_missing_group(db_create_host, api_add_hosts_to_group, event_producer):
    # Create a test group which not exist in database
    missing_group_id = "454dddba-9a4d-42b3-8f16-86a8c1400000"
    host_id_list = [db_create_host().id for _ in range(3)]

    response_status, _ = api_add_hosts_to_group(missing_group_id, [str(host) for host in host_id_list])
    assert response_status == 404


def test_add_missing_host_to_existing_group(db_create_group, api_add_hosts_to_group, event_producer):
    group_id = db_create_group("test_group").id
    host_id_list = [str(uuid.uuid4())]

    response_status, _ = api_add_hosts_to_group(group_id, host_id_list)
    assert response_status == 400


def test_with_empty_data(api_add_hosts_to_group, event_producer):
    response_status, _ = api_add_hosts_to_group(None, None)
    assert response_status == 400


def test_add_empty_body_to_group(db_create_group, api_add_hosts_to_group):
    group_id = db_create_group("test_group").id
    response_status, _ = api_add_hosts_to_group(group_id, None)

    assert response_status == 400


def test_add_empty_array_to_group(db_create_group, api_add_hosts_to_group):
    group_id = db_create_group("test_group").id
    response_status, _ = api_add_hosts_to_group(group_id, [])

    assert response_status == 400

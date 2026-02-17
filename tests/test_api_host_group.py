import uuid
from collections.abc import Callable
from datetime import UTC
from datetime import datetime
from datetime import timedelta

import pytest
from dateutil.parser import parse

from app.exceptions import ResourceNotFoundException
from app.models import Host
from tests.helpers.api_utils import GROUP_URL
from tests.helpers.api_utils import GROUP_WRITE_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_groups_url
from tests.helpers.api_utils import create_mock_rbac_response
from tests.helpers.test_utils import generate_uuid


@pytest.mark.usefixtures("event_producer")
def test_add_host_to_group(db_create_group, db_create_host, db_get_hosts_for_group, api_add_hosts_to_group):
    # Create a group and 3 hosts
    group_id = db_create_group("test_group").id
    host_id_list = [db_create_host().id for _ in range(3)]

    response_status, _ = api_add_hosts_to_group(group_id, [str(host) for host in host_id_list[:2]])
    assert response_status == 200

    # Confirm that the group now only contains  2 hosts
    hosts_after = db_get_hosts_for_group(group_id)
    assert len(hosts_after) == 2
    assert hosts_after[0].id in host_id_list
    assert hosts_after[1].id in host_id_list


@pytest.mark.usefixtures("enable_rbac")
def test_add_host_to_group_RBAC_denied(
    subtests, mocker, db_create_host, db_create_group_with_hosts, api_add_hosts_to_group
):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    group_id = str(db_create_group_with_hosts("new_group", 3).id)

    for response_file in GROUP_WRITE_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)

        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response
            host_id_list = [db_create_host().id for _ in range(3)]
            response_status, _ = api_add_hosts_to_group(group_id, [str(host) for host in host_id_list[:2]])

            assert_response_status(response_status, 403)


@pytest.mark.usefixtures("enable_rbac")
def test_add_host_to_group_RBAC_denied_missing_group(subtests, mocker, db_create_host, api_add_hosts_to_group):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    group_id = str(generate_uuid())

    for response_file in GROUP_WRITE_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)

        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response
            host_id_list = [db_create_host().id for _ in range(3)]
            response_status, _ = api_add_hosts_to_group(group_id, [str(host) for host in host_id_list[:2]])

            assert_response_status(response_status, 404)


@pytest.mark.usefixtures("enable_rbac", "event_producer")
def test_add_host_to_group_RBAC_allowed_specific_groups(
    mocker,
    db_create_group_with_hosts,
    api_add_hosts_to_group,
    db_create_host,
    db_get_hosts_for_group,
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

    response_status, _ = api_add_hosts_to_group(group_id, [str(host) for host in host_id_list[:2]])

    # Should be allowed
    assert_response_status(response_status, 200)
    # Group should now have 5 hosts
    hosts_after = db_get_hosts_for_group(group_id)
    assert len(hosts_after) == 5


@pytest.mark.usefixtures("enable_rbac")
def test_add_host_to_group_RBAC_denied_specific_groups(
    mocker, db_create_group_with_hosts, api_add_hosts_to_group, db_create_host
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

    response_status, _ = api_add_hosts_to_group(group_id, [str(host) for host in host_id_list[:2]])

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
    group = db_create_group("test_group")
    group_id = group.id
    host_id_list = [db_create_host().id for _ in range(3)]

    # Add 1 host to the group
    db_create_host_group_assoc(host_id_list[1], group_id)

    # get update time with 1 host in the group
    first_update = group.modified_on

    # Confirm that the association exists
    hosts_before = db_get_hosts_for_group(group_id)
    assert len(hosts_before) == 1

    # Confirm that the API is allowed to add the hosts even though one is associated
    response_status, updated_group = api_add_hosts_to_group(group_id, [str(host) for host in host_id_list])
    assert response_status == 200

    # Confirm the host count afterwards
    assert len(db_get_hosts_for_group(group_id)) == 3

    # Make sure that the events were produced
    assert event_producer.write_event.call_count == 3

    second_update = parse(updated_group["updated"])
    assert second_update > first_update


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


def test_add_host_in_ungrouped_group_to_new_group(
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
    ungrouped_group_id = db_create_group("ungrouped_group", ungrouped=True).id
    new_group_id = db_create_group("new_group").id
    host_id_list = [str(db_create_host().id) for _ in range(3)]

    # Add the second 2 hosts to a group
    db_create_host_group_assoc(host_id_list[1], ungrouped_group_id)
    db_create_host_group_assoc(host_id_list[2], new_group_id)

    # Confirm that the association exists
    hosts_before = db_get_hosts_for_group(ungrouped_group_id)
    assert len(hosts_before) == 1
    hosts_before = db_get_hosts_for_group(new_group_id)
    assert len(hosts_before) == 1

    # Confirm that the API allows these hosts to be added to the group
    response_status, _ = api_add_hosts_to_group(new_group_id, host_id_list)
    assert response_status == 200

    # Make sure that all 3 hosts are now in the new group
    assert len(db_get_hosts_for_group(new_group_id)) == 3
    assert event_producer.write_event.call_count == 3


@pytest.mark.usefixtures("event_producer")
def test_add_host_list_with_one_associated_host_to_group(
    db_create_group,
    db_create_host,
    db_get_hosts_for_group,
    db_create_host_group_assoc,
    api_add_hosts_to_group,
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


@pytest.mark.usefixtures("event_producer")
def test_add_host_to_missing_group(db_create_host, api_add_hosts_to_group):
    # Create a test group which not exist in database
    missing_group_id = "454dddba-9a4d-42b3-8f16-86a8c1400000"
    host_id_list = [db_create_host().id for _ in range(3)]

    response_status, _ = api_add_hosts_to_group(missing_group_id, [str(host) for host in host_id_list])
    assert response_status == 404


@pytest.mark.usefixtures("event_producer")
def test_add_missing_host_to_existing_group(db_create_group, api_add_hosts_to_group):
    group_id = db_create_group("test_group").id
    host_id_list = [str(uuid.uuid4())]

    response_status, _ = api_add_hosts_to_group(group_id, host_id_list)
    assert response_status == 400


def test_add_valid_host_and_missing_host_to_existing_group(
    db_create_group, db_create_host, db_get_hosts_for_group, api_add_hosts_to_group
):
    group_id = db_create_group("test_group").id
    valid_host_id = str(db_create_host().id)
    missing_host_id = str(generate_uuid())
    host_id_list = [valid_host_id, missing_host_id]

    response_status, _ = api_add_hosts_to_group(group_id, host_id_list)
    assert response_status == 400
    assert len(db_get_hosts_for_group(group_id)) == 0


@pytest.mark.usefixtures("event_producer")
def test_with_empty_data(api_add_hosts_to_group):
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


@pytest.mark.usefixtures("event_producer")
def test_group_with_culled_hosts(
    db_create_group,
    db_create_host,
    db_get_hosts_for_group,
    api_add_hosts_to_group,
    db_get_host: Callable[..., Host],
    api_get,
):
    # Create a group and 3 hosts
    group_id = db_create_group("test_group").id

    host_id_list = [db_create_host().id for _ in range(3)]

    response_status, _ = api_add_hosts_to_group(group_id, [str(host) for host in host_id_list[:3]])
    assert response_status == 200

    # Confirm that the group contains 3 hosts
    _, response_data = api_get(build_groups_url(str(group_id)))
    host_count = response_data["results"][0]["host_count"]
    assert host_count == 3

    hosts_after = db_get_hosts_for_group(group_id)
    assert len(hosts_after) == 3
    culled_host = db_get_host(hosts_after[0].id)

    culled_host.deletion_timestamp = datetime.now(tz=UTC) - timedelta(minutes=5)

    _, response_data = api_get(f"{GROUP_URL}/" + ",".join([str(group_id)]))
    host_count = response_data["results"][0]["host_count"]
    assert host_count == 2


@pytest.mark.parametrize(
    "host_ids",
    [[str(generate_uuid())] * 2, [str(generate_uuid())] + [str(generate_uuid())] * 2],
)
def test_add_host_list_with_duplicate_host_ids(db_create_group, api_add_hosts_to_group, host_ids):
    group_id = db_create_group("test_group").id
    response_status, response_data = api_add_hosts_to_group(group_id, host_ids)
    assert response_status == 400
    assert "Host IDs must be unique." in response_data["detail"]


@pytest.mark.usefixtures("event_producer")
def test_remove_hosts_rbac_v2_workspace_validation_success(
    mocker,
    db_create_group,
    db_create_host,
    db_get_hosts_for_group,
    api_add_hosts_to_group,
    api_remove_hosts_from_group,
):
    """
    Test that DELETE /groups/{group_id}/hosts/{host_id_list} succeeds
    with RBAC v2 workspace validation when workspace exists.

    JIRA: RHINENG-17400
    """
    # Create group and hosts
    group = db_create_group("test_group")
    host1 = db_create_host()
    host2 = db_create_host()
    host3 = db_create_host()

    # Save IDs before session closes
    group_id = group.id
    host1_id = host1.id
    host2_id = host2.id
    host3_id = host3.id

    # Add all 3 hosts to the group first
    response_status, _ = api_add_hosts_to_group(group_id, [str(host1_id), str(host2_id), str(host3_id)])
    assert response_status == 200

    # Verify group has 3 hosts
    hosts_before = db_get_hosts_for_group(group_id)
    assert len(hosts_before) == 3

    # Mock feature flag enabled (RBAC v2 path)
    mock_config = mocker.patch("api.host_group.inventory_config")
    mock_config.return_value.bypass_kessel = False
    mocker.patch("api.host_group.get_flag_value", return_value=True)

    # Mock workspace fetch to return valid workspace
    mock_workspace = {
        "id": str(group_id),
        "name": "test_group",
        "org_id": "12345",
        "type": "standard",
    }
    mocker.patch("api.host_group.get_rbac_workspace_by_id", return_value=mock_workspace)

    # Remove 2 hosts from the group
    response_status, _ = api_remove_hosts_from_group(group_id, [str(host1_id), str(host2_id)])

    # Verify success (204 No Content)
    assert_response_status(response_status, 204)

    # Verify only 1 host remains
    hosts_after = db_get_hosts_for_group(group_id)
    assert len(hosts_after) == 1
    assert hosts_after[0].id == host3_id


def test_remove_hosts_rbac_v2_workspace_not_found(mocker, event_producer, db_create_host, api_remove_hosts_from_group):
    """
    Test that DELETE /groups/{group_id}/hosts/{host_id_list} returns 404
    when workspace not found using RBAC v2.

    JIRA: RHINENG-17400
    """
    # Create valid hosts
    host1 = db_create_host()
    host2 = db_create_host()

    # Save IDs before session closes
    host1_id = host1.id
    host2_id = host2.id

    # Mock event producer
    mocker.patch.object(event_producer, "write_event")

    # Use random group_id that doesn't exist
    invalid_group_id = generate_uuid()

    # Mock feature flag enabled (RBAC v2 path)
    mock_config = mocker.patch("api.host_group.inventory_config")
    mock_config.return_value.bypass_kessel = False
    mocker.patch("api.host_group.get_flag_value", return_value=True)

    # Mock RBAC v2 workspace fetch to raise ResourceNotFoundException (not found)
    mocker.patch(
        "api.host_group.get_rbac_workspace_by_id", side_effect=ResourceNotFoundException("Workspace not found")
    )

    # Try to remove hosts from non-existent group
    response_status, response_data = api_remove_hosts_from_group(invalid_group_id, [str(host1_id), str(host2_id)])

    # Verify 404 error
    assert_response_status(response_status, 404)
    assert "Group" in response_data["detail"] and "not found" in response_data["detail"]


def test_remove_hosts_from_ungrouped_workspace_rbac_v2(
    mocker, event_producer, db_create_group, db_create_host, api_remove_hosts_from_group
):
    """
    Test that DELETE /groups/{group_id}/hosts/{host_id_list} returns 400
    when trying to remove hosts from ungrouped workspace using RBAC v2.

    JIRA: RHINENG-17400
    """
    # Create a group (will pretend it's ungrouped via workspace mock)
    group = db_create_group("ungrouped")
    host1 = db_create_host()

    # Save IDs before session closes
    group_id = group.id
    host1_id = host1.id

    # Mock event producer
    mocker.patch.object(event_producer, "write_event")

    # Mock feature flag enabled (RBAC v2 path)
    mock_config = mocker.patch("api.host_group.inventory_config")
    mock_config.return_value.bypass_kessel = False
    mocker.patch("api.host_group.get_flag_value", return_value=True)

    # Mock workspace fetch to return ungrouped workspace
    mock_workspace = {
        "id": str(group_id),
        "name": "ungrouped",
        "org_id": "12345",
        "type": "ungrouped-hosts",  # This is the key - ungrouped type
    }
    mocker.patch("api.host_group.get_rbac_workspace_by_id", return_value=mock_workspace)

    # Try to remove host from ungrouped workspace
    response_status, response_data = api_remove_hosts_from_group(group_id, [str(host1_id)])

    # Verify 400 error
    assert_response_status(response_status, 400)
    assert "Cannot remove hosts from ungrouped workspace" in response_data["detail"]


@pytest.mark.usefixtures("event_producer")
def test_remove_hosts_feature_flag_disabled(
    mocker,
    db_create_group,
    db_create_host,
    db_get_hosts_for_group,
    api_add_hosts_to_group,
    api_remove_hosts_from_group,
):
    """
    Test that DELETE /groups/{group_id}/hosts/{host_id_list} uses
    database validation when feature flag is disabled (RBAC v1 path).

    JIRA: RHINENG-17400
    """
    # Create group and hosts
    group = db_create_group("test_group")
    host1 = db_create_host()
    host2 = db_create_host()

    # Save IDs before session closes
    group_id = group.id
    host1_id = host1.id
    host2_id = host2.id

    # Add hosts to group
    response_status, _ = api_add_hosts_to_group(group_id, [str(host1_id), str(host2_id)])
    assert response_status == 200

    # Verify group has 2 hosts
    hosts_before = db_get_hosts_for_group(group_id)
    assert len(hosts_before) == 2

    # Mock feature flag disabled (RBAC v1 path)
    mocker.patch("api.host_group.get_flag_value", return_value=False)

    # Remove 1 host from group
    response_status, _ = api_remove_hosts_from_group(group_id, [str(host1_id)])

    # Verify success using database validation
    assert_response_status(response_status, 204)

    # Verify only 1 host remains
    hosts_after = db_get_hosts_for_group(group_id)
    assert len(hosts_after) == 1


def test_remove_invalid_hosts_from_group_rbac_v2(mocker, event_producer, db_create_group, api_remove_hosts_from_group):
    """
    Test that DELETE /groups/{group_id}/hosts/{host_id_list} returns 404
    when trying to remove non-existent hosts from a valid group using RBAC v2.

    JIRA: RHINENG-17400
    """
    # Create a valid group
    group = db_create_group("test_group")
    group_id = group.id

    # Mock event producer
    mocker.patch.object(event_producer, "write_event")

    # Mock feature flag enabled (RBAC v2 path)
    mock_config = mocker.patch("api.host_group.inventory_config")
    mock_config.return_value.bypass_kessel = False
    mocker.patch("api.host_group.get_flag_value", return_value=True)

    # Mock workspace fetch to return valid workspace
    mock_workspace = {
        "id": str(group_id),
        "name": "test_group",
        "org_id": "12345",
        "type": "standard",
    }
    mocker.patch("api.host_group.get_rbac_workspace_by_id", return_value=mock_workspace)

    # Try to remove hosts that don't exist (random UUIDs)
    invalid_host_ids = [str(generate_uuid()), str(generate_uuid())]

    response_status, response_data = api_remove_hosts_from_group(group_id, invalid_host_ids)

    # Verify 404 error - hosts not found
    assert_response_status(response_status, 404)
    assert "Hosts not found" in response_data["detail"]


def test_remove_valid_hosts_from_invalid_group_rbac_v2(
    mocker, event_producer, db_create_host, api_remove_hosts_from_group
):
    """
    Test that DELETE /groups/{group_id}/hosts/{host_id_list} returns 404
    when trying to remove hosts from a non-existent group using RBAC v2.

    JIRA: RHINENG-17400
    """
    # Create valid hosts
    host1 = db_create_host()
    host2 = db_create_host()

    # Save IDs before session closes
    host1_id = host1.id
    host2_id = host2.id

    # Mock event producer
    mocker.patch.object(event_producer, "write_event")

    # Use a random group_id that doesn't exist
    invalid_group_id = generate_uuid()

    # Mock feature flag enabled (RBAC v2 path)
    mock_config = mocker.patch("api.host_group.inventory_config")
    mock_config.return_value.bypass_kessel = False
    mocker.patch("api.host_group.get_flag_value", return_value=True)

    # Mock RBAC v2 workspace fetch to raise ResourceNotFoundException (not found)
    mocker.patch(
        "api.host_group.get_rbac_workspace_by_id", side_effect=ResourceNotFoundException("Workspace not found")
    )

    # Try to remove valid hosts from non-existent group
    response_status, response_data = api_remove_hosts_from_group(invalid_group_id, [str(host1_id), str(host2_id)])

    # Verify 404 error - group not found
    assert_response_status(response_status, 404)
    assert "Group" in response_data["detail"] and "not found" in response_data["detail"]


#
# Tests for GET /groups/{group_id}/hosts endpoint
#


def test_get_hosts_from_group_basic(
    db_create_group, db_create_host, db_create_host_group_assoc, api_get_hosts_from_group
):
    """Test basic functionality of getting hosts from a group"""
    # Create a group and 3 hosts
    group_id = db_create_group("test_group").id
    host_id_list = [db_create_host().id for _ in range(3)]

    # Add 2 hosts to the group
    db_create_host_group_assoc(host_id_list[0], group_id)
    db_create_host_group_assoc(host_id_list[1], group_id)

    # Get hosts from the group
    response_status, response_data = api_get_hosts_from_group(group_id)
    assert response_status == 200
    assert response_data["total"] == 2
    assert response_data["count"] == 2
    assert len(response_data["results"]) == 2

    # Verify the correct hosts are returned
    returned_host_ids = {host["id"] for host in response_data["results"]}
    assert str(host_id_list[0]) in returned_host_ids
    assert str(host_id_list[1]) in returned_host_ids
    assert str(host_id_list[2]) not in returned_host_ids


def test_get_hosts_from_empty_group(db_create_group, api_get_hosts_from_group):
    """Test getting hosts from a group that has no hosts"""
    group_id = db_create_group("empty_group").id

    response_status, response_data = api_get_hosts_from_group(group_id)
    assert response_status == 200
    assert response_data["total"] == 0
    assert response_data["count"] == 0
    assert len(response_data["results"]) == 0


@pytest.mark.parametrize(
    "bypass_kessel,flag_enabled,expect_rbac_call,expect_db_call",
    [
        (True, False, False, True),  # Kessel bypassed, should use DB
        (False, True, True, False),  # Kessel enabled, should call RBAC API
        (False, False, False, True),  # Kessel disabled, should use DB
    ],
    ids=["bypass_kessel", "kessel_enabled", "kessel_disabled"],
)
def test_get_hosts_from_missing_group(
    mocker, api_get_hosts_from_group, bypass_kessel, flag_enabled, expect_rbac_call, expect_db_call
):
    """Test 404 error for nonexistent group across different feature flag states"""
    missing_group_id = "454dddba-9a4d-42b3-8f16-86a8c1400000"

    # Always mock configuration to make test deterministic
    mock_config = mocker.patch("api.host_group.inventory_config")
    mock_config.return_value.bypass_kessel = bypass_kessel
    mocker.patch("api.host_group.get_flag_value", return_value=flag_enabled)

    # Mock RBAC workspace API for Kessel-enabled path
    if expect_rbac_call:
        mock_get_workspace = mocker.patch("api.host_group.get_rbac_workspace_by_id")
        mock_get_workspace.side_effect = ResourceNotFoundException(f"Workspace {missing_group_id} not found")

    # Mock database call for non-Kessel paths
    if expect_db_call:
        mock_get_group_db = mocker.patch("api.host_group.get_group_by_id_from_db")
        mock_get_group_db.return_value = None  # Group not found

    response_status, response_data = api_get_hosts_from_group(missing_group_id)
    assert response_status == 404

    # Verify correct code path was taken
    if expect_rbac_call:
        mock_get_workspace.assert_called_once_with(missing_group_id)
        # DB should NOT be called when RBAC v2 is used
        if "mock_get_group_db" in locals():
            mock_get_group_db.assert_not_called()

    if expect_db_call:
        mock_get_group_db.assert_called_once_with(missing_group_id, mocker.ANY)
        # RBAC API should NOT be called when DB is used
        if "mock_get_workspace" in locals():
            mock_get_workspace.assert_not_called()


def test_get_hosts_from_group_with_pagination(
    db_create_group, db_create_host, db_create_host_group_assoc, api_get_hosts_from_group
):
    """Test pagination parameters work correctly"""
    # Create a group and 5 hosts
    group_id = db_create_group("test_group").id
    host_id_list = [db_create_host().id for _ in range(5)]

    # Add all 5 hosts to the group
    for host_id in host_id_list:
        db_create_host_group_assoc(host_id, group_id)

    # Get first page (2 hosts per page)
    response_status, response_data = api_get_hosts_from_group(group_id, query_parameters={"per_page": 2, "page": 1})
    assert response_status == 200
    assert response_data["total"] == 5
    assert response_data["count"] == 2
    assert response_data["page"] == 1
    assert response_data["per_page"] == 2
    assert len(response_data["results"]) == 2

    # Get second page
    response_status, response_data = api_get_hosts_from_group(group_id, query_parameters={"per_page": 2, "page": 2})
    assert response_status == 200
    assert response_data["total"] == 5
    assert response_data["count"] == 2
    assert response_data["page"] == 2
    assert len(response_data["results"]) == 2

    # Get third page (only 1 host)
    response_status, response_data = api_get_hosts_from_group(group_id, query_parameters={"per_page": 2, "page": 3})
    assert response_status == 200
    assert response_data["total"] == 5
    assert response_data["count"] == 1
    assert response_data["page"] == 3
    assert len(response_data["results"]) == 1


def test_get_hosts_from_group_with_display_name_filter(
    db_create_group, db_create_host, db_create_host_group_assoc, api_get_hosts_from_group
):
    """Test filtering by display_name within a group"""
    # Create a group and 3 hosts with different display names
    group_id = db_create_group("test_group").id
    host1 = db_create_host(extra_data={"display_name": "server-prod-01"})
    host2 = db_create_host(extra_data={"display_name": "server-prod-02"})
    host3 = db_create_host(extra_data={"display_name": "db-dev-01"})

    # Add all to the group
    db_create_host_group_assoc(host1.id, group_id)
    db_create_host_group_assoc(host2.id, group_id)
    db_create_host_group_assoc(host3.id, group_id)

    # Filter by display_name containing "prod"
    response_status, response_data = api_get_hosts_from_group(
        group_id, query_parameters={"display_name": "server-prod"}
    )
    assert response_status == 200
    assert response_data["total"] == 2
    returned_names = {host["display_name"] for host in response_data["results"]}
    assert "server-prod-01" in returned_names
    assert "server-prod-02" in returned_names
    assert "db-dev-01" not in returned_names


@pytest.mark.parametrize(
    "order_how,expected_order",
    [
        ("ASC", ["host-a", "host-b", "host-c"]),
        ("DESC", ["host-c", "host-b", "host-a"]),
    ],
    ids=["ascending", "descending"],
)
def test_get_hosts_from_group_with_ordering(
    db_create_group, db_create_host, db_create_host_group_assoc, api_get_hosts_from_group, order_how, expected_order
):
    """Test ordering hosts by display_name (ASC and DESC)"""
    # Create a group and 3 hosts
    group_id = db_create_group("test_group").id
    host_a = db_create_host(extra_data={"display_name": "host-a"})
    host_b = db_create_host(extra_data={"display_name": "host-b"})
    host_c = db_create_host(extra_data={"display_name": "host-c"})

    # Add in reverse order to test ordering works regardless of insertion order
    db_create_host_group_assoc(host_c.id, group_id)
    db_create_host_group_assoc(host_b.id, group_id)
    db_create_host_group_assoc(host_a.id, group_id)

    # Get hosts with specified ordering
    response_status, response_data = api_get_hosts_from_group(
        group_id, query_parameters={"order_by": "display_name", "order_how": order_how}
    )

    # Verify correct ordering
    assert response_status == 200
    assert len(response_data["results"]) == 3
    for idx, expected_name in enumerate(expected_order):
        assert response_data["results"][idx]["display_name"] == expected_name


@pytest.mark.parametrize(
    "order_param,param_value,expected_error_text",
    [
        ("order_by", "invalid_field", "invalid_field"),
        ("order_how", "SIDEWAYS", "sideways"),
    ],
    ids=["invalid_order_by", "invalid_order_how"],
)
def test_get_hosts_from_group_invalid_ordering(
    db_create_group,
    db_create_host,
    db_create_host_group_assoc,
    api_get_hosts_from_group,
    order_param,
    param_value,
    expected_error_text,
):
    """Test 400 error for invalid ordering parameters"""
    group_id = db_create_group("test_group").id
    host_id = db_create_host().id
    db_create_host_group_assoc(host_id, group_id)

    # Build query parameters with one invalid value
    query_params = {"order_by": "display_name", "order_how": "ASC"}
    query_params[order_param] = param_value

    response_status, response_data = api_get_hosts_from_group(group_id, query_parameters=query_params)
    assert response_status == 400
    assert expected_error_text in response_data["detail"].lower()


@pytest.mark.usefixtures("enable_rbac")
def test_get_hosts_from_group_RBAC_denied(subtests, mocker, db_create_group, api_get_hosts_from_group):
    """Test that RBAC denies access when user lacks read permissions"""
    from tests.helpers.api_utils import HOST_READ_PROHIBITED_RBAC_RESPONSE_FILES

    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    group_id = str(db_create_group("test_group").id)

    for response_file in HOST_READ_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)

        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response
            response_status, _ = api_get_hosts_from_group(group_id)
            assert_response_status(response_status, 403)


@pytest.mark.parametrize(
    "flag_enabled",
    [True, False],
    ids=["kessel_enabled", "kessel_disabled"],
)
def test_get_hosts_from_group_with_kessel_feature_flag(
    mocker, db_create_group, db_create_host, db_create_host_group_assoc, api_get_hosts_from_group, flag_enabled
):
    """Test successful host retrieval with different Kessel feature flag states"""
    # Create a group and host
    group_id = db_create_group("test_group").id
    host = db_create_host()
    db_create_host_group_assoc(host.id, group_id)

    # Mock bypass_kessel=False and flag=flag_enabled
    mock_config = mocker.patch("api.host_group.inventory_config")
    mock_config.return_value.bypass_kessel = False
    mocker.patch("api.host_group.get_flag_value", return_value=flag_enabled)

    if flag_enabled:
        # Mock the RBAC workspace API to return a valid workspace
        mock_get_workspace = mocker.patch("api.host_group.get_rbac_workspace_by_id")
        mock_get_workspace.return_value = {"id": str(group_id), "name": "test_group"}

    # Call the endpoint
    response_status, response_data = api_get_hosts_from_group(group_id)

    # Verify RBAC v2 workspace validation was called if enabled
    if flag_enabled:
        mock_get_workspace.assert_called_once_with(str(group_id))

    # Verify response
    assert response_status == 200
    assert response_data["total"] == 1
    assert len(response_data["results"]) == 1

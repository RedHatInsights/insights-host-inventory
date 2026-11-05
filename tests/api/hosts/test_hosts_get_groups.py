import random
import uuid

import pytest

from tests.helpers.api_utils import RBACFilterOperation
from tests.helpers.api_utils import assert_host_lists_equal
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_expected_host_list
from tests.helpers.api_utils import build_hosts_url
from tests.helpers.api_utils import create_custom_rbac_response


@pytest.mark.parametrize("num_groups", (1, 3, 5))
@pytest.mark.parametrize("group_param_to_use", ("workspace", "group"))
def test_query_using_group_name(db_create_group_with_hosts, api_get, num_groups, group_param_to_use):
    hosts_per_group = 3
    for i in range(num_groups):
        db_create_group_with_hosts(f"existing_group_{i}", hosts_per_group)

    # Some other group that we don't want to see in the response
    db_create_group_with_hosts("some_other_group", 5)

    group_name_params = "&".join([f"{group_param_to_use}_name=EXISTING_GROUP_{i}" for i in range(num_groups)])
    url = build_hosts_url(query=f"?{group_name_params}")

    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == num_groups * hosts_per_group
    for result in response_data["results"]:
        assert "existing_group_" in result["groups"][0]["name"]
        assert result["groups"][0]["ungrouped"] is False


@pytest.mark.parametrize("group_param_to_use", ("workspace", "group"))
def test_query_ungrouped_hosts(
    db_create_group_with_hosts, mq_create_three_specific_hosts, api_get, group_param_to_use
):
    # Create 3 hosts that are not in a group
    ungrouped_hosts = mq_create_three_specific_hosts

    # Also create 5 hosts that are in a group
    db_create_group_with_hosts("group_with_hosts", 5)
    url = build_hosts_url(query=f"?{group_param_to_use}_name=")

    response_status, response_data = api_get(url)

    assert response_status == 200
    assert_host_lists_equal(build_expected_host_list(ungrouped_hosts), response_data["results"])


@pytest.mark.parametrize("ungrouped", (True, False))
@pytest.mark.parametrize("group_param_to_use", ("workspace", "group"))
def test_query_hosts_with_group_data_kessel(ungrouped, db_create_group_with_hosts, api_get, group_param_to_use):
    # Create a host in the "ungrouped" group
    ungrouped_group_id = db_create_group_with_hosts("test_group", 1, ungrouped).id
    url = build_hosts_url(query=f"?{group_param_to_use}_name=test_group")

    response_status, response_data = api_get(url)

    assert response_status == 200
    assert (group_result := response_data["results"][0]["groups"][0])["name"] == "test_group"
    assert group_result["id"] == str(ungrouped_group_id)
    assert group_result["ungrouped"] is ungrouped


@pytest.mark.parametrize("group_param_to_use", ("workspace", "group"))
def test_query_using_group_id(db_create_group_with_hosts, api_get, group_param_to_use):
    """Test filtering hosts by group_id parameter."""
    hosts_per_group = 3
    group1 = db_create_group_with_hosts("test_group_1", hosts_per_group)

    # Create other groups that we don't want in the response
    db_create_group_with_hosts("test_group_2", hosts_per_group)
    db_create_group_with_hosts("other_group", 5)

    # Query using group_id
    url = build_hosts_url(query=f"?{group_param_to_use}_id={group1.id}")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == hosts_per_group
    for result in response_data["results"]:
        assert result["groups"][0]["id"] == str(group1.id)
        assert result["groups"][0]["name"] == "test_group_1"


@pytest.mark.parametrize("group_param_to_use", ("workspace", "group"))
def test_query_using_multiple_group_ids(db_create_group_with_hosts, api_get, group_param_to_use):
    """Test filtering hosts by multiple group_id parameters."""
    hosts_per_group = 3
    group1 = db_create_group_with_hosts("test_group_1", hosts_per_group)
    group2 = db_create_group_with_hosts("test_group_2", hosts_per_group)

    # Create another group that we don't want in the response
    db_create_group_with_hosts("other_group", 5)

    # Query using multiple group_ids
    url = build_hosts_url(query=f"?{group_param_to_use}_id={group1.id}&{group_param_to_use}_id={group2.id}")
    response_status, response_data = api_get(url)

    assert response_status == 200
    assert len(response_data["results"]) == hosts_per_group * 2
    returned_group_ids = {result["groups"][0]["id"] for result in response_data["results"]}
    assert returned_group_ids == {str(group1.id), str(group2.id)}


@pytest.mark.parametrize("group_param_to_use", ("workspace", "group"))
def test_query_group_id_with_duplicate_names(db_create_group_with_hosts, api_get, group_param_to_use):
    """
    Test that group_id filter returns correct hosts even when multiple groups have the same name.
    This is the key requirement from RHINENG-17234: with Kessel, multiple groups can have
    the same name if they have different parents, and filtering by group_id ensures we get
    the correct group's hosts.
    """
    # Create two groups with the same name
    group1 = db_create_group_with_hosts("duplicate_name", 3)
    group2 = db_create_group_with_hosts("duplicate_name", 5)

    # Query using group_id for the first group
    url = build_hosts_url(query=f"?{group_param_to_use}_id={group1.id}")
    response_status, response_data = api_get(url)

    assert response_status == 200
    # Should return only hosts from group1, not group2
    assert len(response_data["results"]) == 3
    for result in response_data["results"]:
        assert result["groups"][0]["id"] == str(group1.id)
        assert result["groups"][0]["name"] == "duplicate_name"

    # Query using group_id for the second group
    url = build_hosts_url(query=f"?{group_param_to_use}_id={group2.id}")
    response_status, response_data = api_get(url)

    assert response_status == 200
    # Should return only hosts from group2, not group1
    assert len(response_data["results"]) == 5
    for result in response_data["results"]:
        assert result["groups"][0]["id"] == str(group2.id)
        assert result["groups"][0]["name"] == "duplicate_name"


@pytest.mark.parametrize("group_param_to_use", ("workspace", "group"))
def test_query_group_name_and_group_id_mutually_exclusive(db_create_group_with_hosts, api_get, group_param_to_use):
    """Test that using both group_name and group_id together returns 400 error."""
    group = db_create_group_with_hosts("test_group", 3)

    # Try using both filters together
    url = build_hosts_url(query=f"?{group_param_to_use}_name=test_group&{group_param_to_use}_id={group.id}")
    response_status, response_data = api_get(url)

    # Should return 400 Bad Request
    assert response_status == 400

    # Verify error message mentions both parameters
    assert f"{group_param_to_use}_name" in response_data["detail"].lower()
    assert f"{group_param_to_use}_id" in response_data["detail"].lower()


def test_query_workspace_and_group_name_mix_not_allowed(db_create_group_with_hosts, api_get):
    """Test that workspace_name and group_name filters cannot be used together."""
    db_create_group_with_hosts("group_a", 2)
    db_create_group_with_hosts("group_b", 2)

    url = build_hosts_url(query="?workspace_name=GROUP_A&group_name=GROUP_B")
    response_status, _ = api_get(url)

    assert response_status == 400


def test_query_workspace_and_group_id_mutually_exclusive(db_create_group_with_hosts, api_get):
    """Test that using both workspace_name and group_id together returns 400 error."""
    group = db_create_group_with_hosts("test_workspace", 3)

    url = build_hosts_url(query=f"?workspace_name=test_workspace&group_id={group.id}")
    response_status, response_data = api_get(url)

    assert response_status == 400
    assert "group_id" in response_data["detail"].lower() or "workspace_id" in response_data["detail"].lower()


@pytest.mark.parametrize("group_param_to_use", ("workspace", "group"))
def test_query_group_id_nonexistent_uuid(api_get, db_create_group_with_hosts, group_param_to_use):
    """Test that a syntactically valid but nonexistent group_id returns no results."""
    # Create some hosts in an existing group so we have data present
    db_create_group_with_hosts("existing_group", 3)

    # Use a random UUID that does not correspond to any group
    nonexistent_workspace_id = str(uuid.uuid4())
    url = build_hosts_url(query=f"?{group_param_to_use}_id={nonexistent_workspace_id}")
    response_status, response_data = api_get(url)

    # Expected behavior: 200 OK with no matching results
    assert response_status == 200
    assert response_data["results"] == []


@pytest.mark.usefixtures("enable_kessel")
@pytest.mark.parametrize("order_how", ("ASC", "DESC"))
def test_get_hosts_order_by_group_name(db_create_group_with_hosts, api_get, order_how):
    hosts_per_group = 3
    num_ungrouped_hosts = 5
    names = ["ABC Group", "BCD Group", "CDE Group", "DEF Group"]
    num_grouped_hosts = hosts_per_group * len(names)

    # Shuffle the list so the groups aren't created in alphabetical order
    # Just to make sure it's actually ordering by name and not date
    shuffled_group_names = names.copy()
    random.shuffle(shuffled_group_names)
    [db_create_group_with_hosts(group_name, hosts_per_group) for group_name in shuffled_group_names]

    # Create some ungrouped hosts
    db_create_group_with_hosts("ungrouped", num_ungrouped_hosts, True)

    url = build_hosts_url(query=f"?order_by=group_name&order_how={order_how}")

    response_status, response_data = api_get(url)

    assert response_status == 200
    assert num_grouped_hosts + num_ungrouped_hosts == len(response_data["results"])

    if order_how == "DESC":
        num_grouped_hosts = hosts_per_group * len(names)
        for group_index in range(num_grouped_hosts, num_grouped_hosts + num_ungrouped_hosts):
            assert response_data["results"][group_index]["groups"][0]["name"] == "ungrouped"
    else:
        # Ungrouped hosts whould be at the top of the list
        for group_index in range(0, num_ungrouped_hosts):
            assert response_data["results"][group_index]["groups"][0]["name"] == "ungrouped"


@pytest.mark.usefixtures("enable_rbac")
@pytest.mark.parametrize("rbac_operation", [RBACFilterOperation.EQUAL, RBACFilterOperation.IN])
def test_get_ungrouped_hosts_granular_rbac(
    db_create_host, db_create_group, db_create_host_group_assoc, api_get, mocker, rbac_operation
):
    # Create the groups
    ungrouped_group_id = db_create_group("ungrouped", ungrouped=True).id
    grouped_group_id = db_create_group("grouped", ungrouped=False).id

    # Create hosts
    ungrouped_host_ids = [str(db_create_host().id) for _ in range(3)]
    ungrouped_group_host_ids = [str(db_create_host().id) for _ in range(4)]
    grouped_host_ids = [str(db_create_host().id) for _ in range(5)]

    # Assign assign hosts to the "ungrouped" group
    for host_id in ungrouped_group_host_ids:
        db_create_host_group_assoc(host_id, ungrouped_group_id)

    # Assign hosts to the regular group
    for host_id in grouped_host_ids:
        db_create_host_group_assoc(host_id, grouped_group_id)

    # Mock RBAC perms; only grant access to ungrouped hosts
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    get_rbac_permissions_mock.return_value = create_custom_rbac_response([None], rbac_operation)

    response_status, response_data = api_get(build_hosts_url())
    assert_response_status(response_status, 200)

    actual_host_ids = [host["id"] for host in response_data["results"]]

    # Make sure it returned only ungrouped hosts and hosts in the "ungrouped" group
    for host_id in ungrouped_host_ids + ungrouped_group_host_ids:
        assert host_id in actual_host_ids

    for host_id in grouped_host_ids:
        assert host_id not in actual_host_ids

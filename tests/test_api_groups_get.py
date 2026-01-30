import pytest

from tests.helpers.api_utils import GROUP_READ_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import GROUP_URL
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_groups_url
from tests.helpers.api_utils import create_mock_rbac_response
from tests.helpers.test_utils import generate_uuid


def test_basic_group_query(db_create_group, api_get):
    group_id_list = [str(db_create_group(f"testGroup_{idx}").id) for idx in range(3)]

    response_status, response_data = api_get(build_groups_url())

    assert_response_status(response_status, 200)
    assert response_data["total"] == 3
    assert response_data["count"] == 3
    for group_result in response_data["results"]:
        assert group_result["id"] in group_id_list


@pytest.mark.parametrize("group_type, expected_groups", (("standard", 2), ("ungrouped-hosts", 1), ("all", 3)))
def test_group_query_type_filter(db_create_group, api_get, group_type, expected_groups):
    group_id_list_dict = {
        "standard": [str(db_create_group(f"testGroup_{idx}").id) for idx in range(2)],
        "ungrouped-hosts": [str(db_create_group("ungroupedTest", ungrouped=True).id)],
    }

    response_status, response_data = api_get(build_groups_url(query=f"?group_type={group_type}"))

    assert_response_status(response_status, 200)
    assert response_data["total"] == expected_groups
    assert response_data["count"] == expected_groups
    if group_type != "all":
        for group_result in response_data["results"]:
            assert group_result["id"] in group_id_list_dict[group_type]


@pytest.mark.usefixtures("enable_rbac")
def test_get_groups_RBAC_denied(subtests, mocker, api_get):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    for response_file in GROUP_READ_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)

        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            response_status, _ = api_get(build_groups_url())

            assert_response_status(response_status, 403)


@pytest.mark.usefixtures("enable_rbac")
def test_get_groups_RBAC_allowed_specific_groups(mocker, db_create_group, api_get):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    group_id_list = [str(db_create_group(f"testGroup_{idx}").id) for idx in range(5)]

    # Grant permission to first 2 groups
    mock_rbac_response = create_mock_rbac_response(
        "tests/helpers/rbac-mock-data/inv-groups-read-resource-defs-template.json"
    )
    mock_rbac_response[0]["resourceDefinitions"][0]["attributeFilter"]["value"] = group_id_list[:2]

    get_rbac_permissions_mock.return_value = mock_rbac_response

    response_status, response_data = api_get(build_groups_url())

    assert_response_status(response_status, 200)
    assert response_data["total"] == 2
    assert response_data["count"] == 2
    for group_result in response_data["results"]:
        assert group_result["id"] in group_id_list


@pytest.mark.parametrize("search", ["testGroup", "TesT", "Group", "ro"])
def test_query_variables_group_name(db_create_group, api_get, search):
    group_id = db_create_group("testGroup").id
    query = f"?name={search}"

    response_status, response_data = api_get(build_groups_url(query=query))

    assert_response_status(response_status, 200)
    assert response_data["total"] == 1
    assert response_data["count"] == 1
    assert response_data["results"][0]["id"] == str(group_id)


@pytest.mark.parametrize(
    "order_how_query,reverse_list",
    [
        (
            "&order_how=ASC",
            False,
        ),
        (
            "&order_how=DESC",
            True,
        ),
        (
            "",
            False,
        ),
    ],
)
def test_sort_by_name(db_create_group, api_get, order_how_query, reverse_list):
    num_groups = 5

    # Create a list of groups. The names have an int appended for easier sorting.
    group_id_list = [str(db_create_group(f"testGroup{idx}").id) for idx in range(num_groups)]

    # If ordering in descending order, we expect the groups in reverse order.
    if reverse_list:
        group_id_list.reverse()

    query = f"?order_by=name{order_how_query}"

    response_status, response_data = api_get(build_groups_url(query=query))

    assert_response_status(response_status, 200)
    assert response_data["total"] == num_groups
    assert response_data["count"] == num_groups
    for idx in range(num_groups):
        assert response_data["results"][idx]["id"] == group_id_list[idx]


@pytest.mark.parametrize("order_how", ["ASC", "DESC"])
def test_sort_by_updated_time(db_create_group, api_get, order_how):
    num_groups = 5
    sort_query = f"?order_by=updated&order_how={order_how}"

    for idx in range(num_groups):
        db_create_group(f"testGroup{idx}")

    response_status, response_data = api_get(build_groups_url(query=sort_query))

    assert_response_status(response_status, 200)
    assert response_data["total"] == num_groups
    assert response_data["count"] == num_groups

    updated_times_list = [group["updated"] for group in response_data["results"]]

    # set the list members in ascending order
    assert updated_times_list == sorted(updated_times_list, reverse=(order_how == "DESC"))


@pytest.mark.parametrize(
    "order_how_query,reverse_list",
    [
        (
            "&order_how=ASC",
            False,
        ),
        (
            "&order_how=DESC",
            True,
        ),
        (
            "",
            True,
        ),
    ],
)
def test_sort_by_host_count(
    db_create_group_with_hosts, api_get, db_get_hosts_for_group, order_how_query, reverse_list
):
    num_groups = 5

    # Create a list of groups. The names are randomized, but each group has one more host than the previous.
    group_id_list = [str(db_create_group_with_hosts(f"group{generate_uuid()}", idx).id) for idx in range(num_groups)]

    # If ordering in descending order, we expect the groups in reverse order.
    if reverse_list:
        group_id_list.reverse()

    query = f"?order_by=host_count{order_how_query}"
    response_status, response_data = api_get(build_groups_url(query=query))

    assert_response_status(response_status, 200)
    assert response_data["total"] == num_groups
    assert response_data["count"] == num_groups
    for idx in range(num_groups):
        group_data = response_data["results"][idx]
        assert group_data["id"] == group_id_list[idx]
        assert group_data["host_count"] == len(db_get_hosts_for_group(group_id_list[idx]))


def test_query_variables_group_name_not_found(db_create_group, api_get):
    db_create_group("testGroup")
    query = "?name=different_group"

    response_status, response_data = api_get(build_groups_url(query=query))

    assert_response_status(response_status, 200)
    assert response_data["total"] == 0
    assert response_data["count"] == 0
    assert len(response_data["results"]) == 0


@pytest.mark.parametrize(
    "num_groups",
    [1, 3, 5],
)
def test_group_id_list_filter(num_groups, db_create_group, api_get):
    group_id_list = [str(db_create_group(f"testGroup_{idx}").id) for idx in range(num_groups)]
    # Create extra groups to filter out
    for idx in range(10):
        db_create_group(f"extraGroup_{idx}")

    response_status, response_data = api_get(GROUP_URL + "/" + ",".join(group_id_list))

    assert response_status == 200
    assert response_data["total"] == num_groups
    assert response_data["count"] == num_groups
    assert len(response_data["results"]) == num_groups
    for group_result in response_data["results"]:
        assert group_result["id"] in group_id_list


def test_group_id_list_filter_not_found(db_create_group, api_get):
    # Create extra groups to filter out
    for idx in range(10):
        db_create_group(f"extraGroup_{idx}")

    response_status, _ = api_get(f"{GROUP_URL}/{generate_uuid()}")
    assert response_status == 404


def test_group_query_pagination(subtests, db_create_group, api_get):
    num_groups = 40
    for idx in range(num_groups):
        # Use leading zeros so that we can sort by name
        db_create_group(f"testGroup_{idx:03}")

    for per_page in [1, 5, 10]:
        for page in [1, 2, 3]:
            with subtests.test():
                query = f"?page={page}&per_page={per_page}&order_by=name"
                response_status, response_data = api_get(build_groups_url(query=query))

                assert response_status == 200
                assert response_data["total"] == num_groups
                assert response_data["count"] == per_page
                assert len(response_data["results"]) == per_page
                for idx in range(per_page):
                    assert response_data["results"][idx]["name"] == f"testGroup_{((page - 1) * per_page + idx):03}"


@pytest.mark.parametrize(
    "order_how_query,reverse_list",
    [
        (
            "&order_how=ASC",
            False,
        ),
        (
            "&order_how=DESC",
            True,
        ),
    ],
)
def test_sort_by_host_count_with_pagination(
    subtests, db_create_group_with_hosts, api_get, order_how_query, reverse_list
):
    """
    Create groups with hosts using tuples
    return group ids and sort it as expected
    each group id is in its right index inside the group_id_list
    mimicing the API respose
    """

    group_id_list = []
    groups_set = [(4, 0), (3, 1), (2, 2)]

    if reverse_list:
        groups_set.reverse()

    for group_set in groups_set:
        num_groups = group_set[0]
        num_hosts = group_set[1]
        temp_id_list = [
            str(db_create_group_with_hosts(f"group{generate_uuid()}", num_hosts).id) for idx in range(num_groups)
        ]
        temp_id_list.sort()
        group_id_list += temp_id_list

    for per_page in [2, 3]:
        start = 0
        end = per_page
        for page in [1, 2, 3]:
            with subtests.test():
                query = f"?page={page}&per_page={per_page}&order_by=host_count{order_how_query}"
                response_status, response_data = api_get(build_groups_url(query=query))
                assert response_status == 200
                assert response_data["total"] == len(group_id_list)
                assert response_data["count"] == per_page
                assert len(response_data["results"]) == per_page
                res = [d["id"] for d in response_data["results"]]  # Get only the ids from the results array
                assert res == group_id_list[start:end]  # compare the ids with the group_id_list
                start = end
                end = end + per_page


# ============================================================================
# RBAC v2 (Kessel) Integration Tests
# ============================================================================
# These tests verify the RBAC v2 code path when FLAG_INVENTORY_KESSEL_PHASE_1
# feature flag is enabled, ensuring get_rbac_workspaces() is called correctly
# with proper parameters including ordering support.
# ============================================================================


def _create_mock_workspace(workspace_id=None, name="test_group", workspace_type="standard"):
    """Helper to create a mock workspace with all required fields."""
    return {
        "id": workspace_id or str(generate_uuid()),
        "name": name,
        "type": workspace_type,
        "created": "2024-01-01T00:00:00.000000+00:00",
        "modified": "2024-01-02T00:00:00.000000+00:00",
        "description": "Test workspace",
        "parent_id": None,
    }


@pytest.mark.parametrize("flag_enabled", [True, False])
def test_get_groups_rbac_v2_flag_toggle(mocker, db_create_group, api_get, flag_enabled):
    """
    Test GET /groups with RBAC v2 feature flag enabled/disabled.
    Verifies correct code path (get_rbac_workspaces vs get_filtered_group_list_db).
    """
    # Mock feature flag
    mocker.patch("api.group.get_flag_value", return_value=flag_enabled)

    if flag_enabled:
        # RBAC v2 path: Mock get_rbac_workspaces to return sample workspaces
        mock_workspaces = [
            _create_mock_workspace(name="group1"),
            _create_mock_workspace(name="group2"),
        ]
        mock_get_rbac_workspaces = mocker.patch("api.group.get_rbac_workspaces")
        mock_get_rbac_workspaces.return_value = (mock_workspaces, 2)

        response_status, response_data = api_get(build_groups_url())

        # Verify response
        assert_response_status(response_status, 200)
        assert response_data["total"] == 2
        assert response_data["count"] == 2
        assert len(response_data["results"]) == 2
        assert response_data["results"][0]["name"] == "group1"
        assert response_data["results"][1]["name"] == "group2"

        # Verify get_rbac_workspaces was called
        assert mock_get_rbac_workspaces.called
    else:
        # RBAC v1 path: Create groups in database
        group_id_list = [str(db_create_group(f"testGroup_{idx}").id) for idx in range(3)]

        # Mock get_rbac_workspaces (should NOT be called)
        mock_get_rbac_workspaces = mocker.patch("api.group.get_rbac_workspaces")

        response_status, response_data = api_get(build_groups_url())

        # Verify response uses database data
        assert_response_status(response_status, 200)
        assert response_data["total"] == 3
        assert response_data["count"] == 3
        for group_result in response_data["results"]:
            assert group_result["id"] in group_id_list

        # Verify get_rbac_workspaces was NOT called (database path used)
        assert not mock_get_rbac_workspaces.called


@pytest.mark.parametrize(
    "order_by,order_how",
    [
        ("name", "ASC"),
        ("name", "DESC"),
        ("updated", "ASC"),
        ("updated", "DESC"),
        ("host_count", "ASC"),
        ("host_count", "DESC"),
    ],
)
def test_get_groups_rbac_v2_with_ordering(mocker, api_get, order_by, order_how):
    """
    Test GET /groups with RBAC v2 and ordering parameters.
    Verifies that order_by and order_how are passed correctly to get_rbac_workspaces().

    Note: The GET /groups API spec allows ordering by: name, host_count, updated.
    """
    # Mock feature flag enabled
    mocker.patch("api.group.get_flag_value", return_value=True)

    # Mock get_rbac_workspaces
    mock_get_rbac_workspaces = mocker.patch("api.group.get_rbac_workspaces")
    mock_get_rbac_workspaces.return_value = ([], 0)

    # Call endpoint with ordering
    query = f"?order_by={order_by}&order_how={order_how}"
    response_status, response_data = api_get(build_groups_url(query=query))

    assert_response_status(response_status, 200)

    # Verify get_rbac_workspaces was called with correct parameters
    assert mock_get_rbac_workspaces.called
    call_args = mock_get_rbac_workspaces.call_args

    # Check positional arguments (name, page, per_page, rbac_filter, group_type, order_by, order_how)
    assert call_args[0][5] == order_by  # order_by is 6th positional arg (index 5)
    assert call_args[0][6] == order_how  # order_how is 7th positional arg (index 6)


@pytest.mark.parametrize(
    "param_name,query_string,expected_arg_index,expected_value",
    [
        ("name", "?name=testGroup", 0, "testGroup"),
        ("group_type_standard", "?group_type=standard", 4, "standard"),
        ("group_type_ungrouped", "?group_type=ungrouped-hosts", 4, "ungrouped-hosts"),
        ("pagination", "?page=2&per_page=5", None, None),  # Special case: checks page and per_page
    ],
)
def test_get_groups_rbac_v2_parameter_passing(
    mocker, api_get, param_name, query_string, expected_arg_index, expected_value
):
    """
    Test GET /groups with RBAC v2 and various query parameters.
    Verifies that parameters are correctly passed to get_rbac_workspaces().
    """
    # Mock feature flag enabled
    mocker.patch("api.group.get_flag_value", return_value=True)

    # Mock get_rbac_workspaces
    if param_name == "pagination":
        mock_workspaces = [_create_mock_workspace(name=f"group{i}") for i in range(5)]
        mock_get_rbac_workspaces = mocker.patch("api.group.get_rbac_workspaces")
        mock_get_rbac_workspaces.return_value = (mock_workspaces[:5], 20)  # 5 results, 20 total
    elif param_name == "name":
        mock_workspaces = [_create_mock_workspace(name=expected_value)]
        mock_get_rbac_workspaces = mocker.patch("api.group.get_rbac_workspaces")
        mock_get_rbac_workspaces.return_value = (mock_workspaces, 1)
    else:  # group_type
        mock_workspaces = [_create_mock_workspace(name="testGroup", workspace_type=expected_value)]
        mock_get_rbac_workspaces = mocker.patch("api.group.get_rbac_workspaces")
        mock_get_rbac_workspaces.return_value = (mock_workspaces, 1)

    # Call with parameter
    response_status, response_data = api_get(build_groups_url(query=query_string))

    assert_response_status(response_status, 200)

    # Verify parameter was passed to get_rbac_workspaces
    assert mock_get_rbac_workspaces.called
    call_args = mock_get_rbac_workspaces.call_args

    if param_name == "pagination":
        # Special case: check both page and per_page
        assert call_args[0][1] == 2  # page is 2nd positional arg (index 1)
        assert call_args[0][2] == 5  # per_page is 3rd positional arg (index 2)
        assert response_data["page"] == 2
        assert response_data["per_page"] == 5
    else:
        # Standard parameter check
        assert call_args[0][expected_arg_index] == expected_value


@pytest.mark.usefixtures("enable_rbac")
def test_get_groups_rbac_v2_with_rbac_filter(mocker, api_get):
    """
    Test GET /groups with RBAC v2 and RBAC filter applied.
    Verifies that RBAC filter is passed to get_rbac_workspaces().
    """
    # Mock feature flag enabled
    mocker.patch("api.group.get_flag_value", return_value=True)

    # Mock RBAC permissions
    group_id_1 = str(generate_uuid())
    group_id_2 = str(generate_uuid())
    mock_rbac_response = [
        {
            "permission": "inventory:groups:read",
            "resourceDefinitions": [
                {
                    "attributeFilter": {
                        "key": "group.id",
                        "operation": "in",
                        "value": [group_id_1, group_id_2],
                    }
                }
            ],
        }
    ]
    mocker.patch("lib.middleware.get_rbac_permissions", return_value=mock_rbac_response)

    # Mock get_rbac_workspaces
    mock_workspaces = [
        _create_mock_workspace(workspace_id=group_id_1, name="group1"),
        _create_mock_workspace(workspace_id=group_id_2, name="group2"),
    ]
    mock_get_rbac_workspaces = mocker.patch("api.group.get_rbac_workspaces")
    mock_get_rbac_workspaces.return_value = (mock_workspaces, 2)

    response_status, response_data = api_get(build_groups_url())

    assert_response_status(response_status, 200)
    assert response_data["total"] == 2

    # Verify get_rbac_workspaces was called with rbac_filter
    assert mock_get_rbac_workspaces.called
    call_args = mock_get_rbac_workspaces.call_args
    rbac_filter = call_args[0][3]  # rbac_filter is 4th positional arg (index 3)
    assert rbac_filter is not None
    assert "groups" in rbac_filter
    assert group_id_1 in rbac_filter["groups"]
    assert group_id_2 in rbac_filter["groups"]


def test_get_groups_rbac_v2_empty_results(mocker, api_get):
    """
    Test GET /groups with RBAC v2 when no groups are found.
    Verifies proper handling of empty results from get_rbac_workspaces().
    """
    # Mock feature flag enabled
    mocker.patch("api.group.get_flag_value", return_value=True)

    # Mock get_rbac_workspaces returning empty results
    mock_get_rbac_workspaces = mocker.patch("api.group.get_rbac_workspaces")
    mock_get_rbac_workspaces.return_value = ([], 0)

    response_status, response_data = api_get(build_groups_url(query="?name=nonexistent"))

    assert_response_status(response_status, 200)
    assert response_data["total"] == 0
    assert response_data["count"] == 0
    assert len(response_data["results"]) == 0


# ============================================================================
# RBAC v2 Negative Tests
# ============================================================================


def test_get_groups_rbac_v2_api_connection_error(mocker, api_get):
    """
    Test GET /groups when RBAC v2 API connection fails.
    Should return 503 Service Unavailable when RBAC v2 API is unreachable.
    """
    mocker.patch("api.group.get_flag_value", return_value=True)

    from requests.exceptions import ConnectionError

    mocker.patch(
        "api.group.get_rbac_workspaces",
        side_effect=ConnectionError("Failed to connect to RBAC v2 API"),
    )

    response_status, response_data = api_get(build_groups_url())

    assert_response_status(response_status, 503)


def test_get_groups_rbac_v2_api_timeout(mocker, api_get):
    """
    Test GET /groups when RBAC v2 API request times out.
    Should return 503 Service Unavailable when RBAC v2 API times out.
    """
    mocker.patch("api.group.get_flag_value", return_value=True)

    from requests.exceptions import Timeout

    mocker.patch(
        "api.group.get_rbac_workspaces",
        side_effect=Timeout("RBAC v2 API request timed out"),
    )

    response_status, response_data = api_get(build_groups_url())

    assert_response_status(response_status, 503)


def test_get_groups_rbac_v2_invalid_order_by(mocker, api_get):
    """
    Test GET /groups with invalid order_by parameter.

    High Priority: Validates API contract and parameter validation.
    Should return 400 Bad Request for unsupported ordering fields.
    """
    # Mock feature flag enabled
    mocker.patch("api.group.get_flag_value", return_value=True)

    # Try to order by invalid field (not in API spec)
    query = "?order_by=invalid_field"
    response_status, response_data = api_get(build_groups_url(query=query))

    # API spec validation should reject this before calling get_rbac_workspaces
    assert_response_status(response_status, 400)
    assert "order_by" in response_data["detail"] or "invalid_field" in response_data["detail"]


@pytest.mark.usefixtures("enable_rbac")
def test_get_groups_rbac_v2_no_workspace_permissions(mocker, api_get):
    """
    Test GET /groups when user has no workspace read permissions.

    High Priority: Important RBAC authorization scenario.
    Should return empty results when user is not authorized to view any workspaces.
    """
    # Mock feature flag enabled
    mocker.patch("api.group.get_flag_value", return_value=True)

    # Mock RBAC permissions with empty resource definitions (no workspaces accessible)
    mock_rbac_response = [{"permission": "inventory:groups:read", "resourceDefinitions": []}]
    mocker.patch("lib.middleware.get_rbac_permissions", return_value=mock_rbac_response)

    # Mock get_rbac_workspaces returning empty results (filtered by RBAC)
    mock_get_rbac_workspaces = mocker.patch("api.group.get_rbac_workspaces")
    mock_get_rbac_workspaces.return_value = ([], 0)

    response_status, response_data = api_get(build_groups_url())

    # Should return 200 with empty results (not 403)
    # RBAC filtering returns empty list, not an error
    assert_response_status(response_status, 200)
    assert response_data["total"] == 0
    assert response_data["count"] == 0
    assert len(response_data["results"]) == 0

    # Verify get_rbac_workspaces was called
    assert mock_get_rbac_workspaces.called


def test_get_groups_rbac_v2_malformed_workspace_response(mocker, api_get):
    """
    Test GET /groups when RBAC v2 API returns malformed workspace data.

    Medium Priority: Tests error handling for invalid RBAC v2 responses.
    Should handle gracefully when workspace objects are missing required fields.
    """
    # Mock feature flag enabled
    mocker.patch("api.group.get_flag_value", return_value=True)

    # Mock malformed workspace (missing required 'id' field)
    mock_workspaces = [
        {
            "name": "group1",
            "type": "standard",
            # Missing 'id' field - should cause serialization error
        }
    ]
    mock_get_rbac_workspaces = mocker.patch("api.group.get_rbac_workspaces")
    mock_get_rbac_workspaces.return_value = (mock_workspaces, 1)

    response_status, response_data = api_get(build_groups_url())

    # Should either:
    # - Return 500 Internal Server Error (serialization failure)
    # - Return 200 with empty results (skip invalid entries)
    assert response_status in [200, 500]

    if response_status == 200:
        # If handled gracefully, should have empty results
        assert response_data["total"] == 0 or response_data["count"] == 0

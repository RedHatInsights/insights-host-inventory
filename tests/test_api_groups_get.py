import pytest
from requests.exceptions import ConnectionError
from requests.exceptions import Timeout
from sqlalchemy.exc import OperationalError

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


def test_group_id_not_found_response_includes_missing_ids(api_get):
    # Verify that 404 response includes the not_found_ids field
    group_id = generate_uuid()

    response_status, response_data = api_get(f"{GROUP_URL}/{group_id}")

    assert response_status == 404
    assert "not_found_ids" in response_data
    assert response_data["not_found_ids"] == [group_id]
    assert response_data["detail"] == "One or more groups not found."


def test_group_ids_not_found_omits_missing_ids_when_results_incomplete(api_get, db_create_group):
    """
    For list-by-ID, when the underlying query reports multiple pages (via total)
    and not all results are available, verify that we return a 404 with only a
    generic detail message and without not_found_ids.
    """
    # Create enough groups so that the underlying search has multiple pages
    group_id_1 = str(db_create_group("group1").id)
    group_id_2 = str(db_create_group("group2").id)

    # Include at least one missing ID in the list
    missing_group_id = str(generate_uuid())
    requested_ids = ",".join([group_id_1, group_id_2, missing_group_id])

    # Use a small page size to ensure total > len(results on this page)
    response_status, response_data = api_get(f"{GROUP_URL}/{requested_ids}?per_page=1")

    assert response_status == 404
    # When results are incomplete, check_all_ids_found should *not* include not_found_ids
    assert "not_found_ids" not in response_data
    assert response_data["detail"] == "One or more groups not found."


def test_mixed_valid_and_missing_group_ids_response_includes_only_missing_ids(db_create_group, api_get):
    # Verify 404 response only includes the missing IDs, not the valid ones
    valid_group_id = str(db_create_group("test_group").id)
    missing_group_id = generate_uuid()

    response_status, response_data = api_get(f"{GROUP_URL}/{valid_group_id},{missing_group_id}")

    assert response_status == 404
    assert "not_found_ids" in response_data
    assert response_data["not_found_ids"] == [missing_group_id]
    assert valid_group_id not in response_data["not_found_ids"]


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
        ("created", "ASC"),
        ("created", "DESC"),
        ("type", "ASC"),
        ("type", "DESC"),
    ],
)
def test_get_groups_rbac_v2_with_ordering(mocker, api_get, order_by, order_how):
    """
    Test GET /groups with RBAC v2 and ordering parameters.
    Verifies that order_by and order_how are passed correctly to get_rbac_workspaces().

    Note: The GET /groups API spec allows ordering by: name, host_count, updated, created, type.
    However, host_count uses a special code path (client-side sorting) and is tested separately
    in test_get_groups_rbac_v2_ordering_by_host_count() and related tests.
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


@pytest.mark.parametrize("order_how", ["ASC", "DESC"])
def test_get_groups_rbac_v2_ordering_by_host_count(mocker, api_get, order_how):
    """
    Test GET /groups with RBAC v2 and order_by=host_count.

    CRITICAL TEST: Verifies that ordering by host_count works correctly with RBAC v2.

    The challenge: RBAC v2 API doesn't know about host counts (they're in host-inventory DB).
    Expected behavior: Backend should fetch workspaces from RBAC v2, add host counts from
    DB, then sort in Python by host_count before returning results.

    This test will FAIL if the code incorrectly relies on RBAC v2 API to sort by host_count.
    """
    # Mock feature flag enabled
    mocker.patch("api.group.get_flag_value", return_value=True)

    # Create mock workspaces in a specific order (by name)
    # RBAC v2 API would return these in this order
    mock_workspaces = [
        _create_mock_workspace(name="group_a", workspace_id=str(generate_uuid())),  # Will have 10 hosts
        _create_mock_workspace(name="group_b", workspace_id=str(generate_uuid())),  # Will have 5 hosts
        _create_mock_workspace(name="group_c", workspace_id=str(generate_uuid())),  # Will have 15 hosts
    ]

    # Mock get_rbac_workspaces to return workspaces in name order
    mock_get_rbac_workspaces = mocker.patch("api.group.get_rbac_workspaces")
    mock_get_rbac_workspaces.return_value = (mock_workspaces, 3)

    # Mock host counts - different from name order!
    # group_a: 10 hosts, group_b: 5 hosts, group_c: 15 hosts
    host_counts = {
        mock_workspaces[0]["id"]: 10,  # group_a
        mock_workspaces[1]["id"]: 5,  # group_b
        mock_workspaces[2]["id"]: 15,  # group_c
    }

    # Mock the batch host count function instead of individual calls
    mocker.patch(
        "api.group.get_host_counts_batch",
        return_value=host_counts,
    )

    # Execute test
    query = f"?order_by=host_count&order_how={order_how}"
    response_status, response_data = api_get(build_groups_url(query=query))

    assert_response_status(response_status, 200)
    assert response_data["total"] == 3
    assert response_data["count"] == 3

    # Verify results are ordered correctly
    results = response_data["results"]

    if order_how == "ASC":
        # Expected order (ASC): group_b (5), group_a (10), group_c (15)
        assert results[0]["name"] == "group_b" and results[0]["host_count"] == 5
        assert results[1]["name"] == "group_a" and results[1]["host_count"] == 10
        assert results[2]["name"] == "group_c" and results[2]["host_count"] == 15
    else:  # DESC
        # Expected order (DESC): group_c (15), group_a (10), group_b (5)
        assert results[0]["name"] == "group_c" and results[0]["host_count"] == 15
        assert results[1]["name"] == "group_a" and results[1]["host_count"] == 10
        assert results[2]["name"] == "group_b" and results[2]["host_count"] == 5


@pytest.mark.parametrize("order_how", ["ASC", "DESC"])
def test_get_groups_rbac_v2_ordering_by_host_count_with_ties(mocker, api_get, order_how):
    """
    Test ordering by host_count when multiple groups have the same host_count.

    EDGE CASE: Verifies secondary sort by name (alphabetical) when host_counts are equal.
    Groups with same host_count should be ordered alphabetically by name.
    """
    # Mock feature flag enabled
    mocker.patch("api.group.get_flag_value", return_value=True)

    # Create mock workspaces - some with same host counts
    mock_workspaces = [
        _create_mock_workspace(name="zebra_group", workspace_id=str(generate_uuid())),  # 10 hosts
        _create_mock_workspace(name="alpha_group", workspace_id=str(generate_uuid())),  # 10 hosts (tie!)
        _create_mock_workspace(name="beta_group", workspace_id=str(generate_uuid())),  # 5 hosts
        _create_mock_workspace(name="gamma_group", workspace_id=str(generate_uuid())),  # 10 hosts (tie!)
    ]

    mock_get_rbac_workspaces = mocker.patch("api.group.get_rbac_workspaces")
    mock_get_rbac_workspaces.return_value = (mock_workspaces, 4)

    # Mock host counts: Three groups with 10 hosts, one with 5
    host_counts = {
        mock_workspaces[0]["id"]: 10,  # zebra
        mock_workspaces[1]["id"]: 10,  # alpha (same as zebra)
        mock_workspaces[2]["id"]: 5,  # beta
        mock_workspaces[3]["id"]: 10,  # gamma (same as zebra and alpha)
    }

    # Mock the batch host count function instead of individual calls
    mocker.patch(
        "api.group.get_host_counts_batch",
        return_value=host_counts,
    )

    # Execute test
    query = f"?order_by=host_count&order_how={order_how}"
    response_status, response_data = api_get(build_groups_url(query=query))

    assert_response_status(response_status, 200)
    results = response_data["results"]

    if order_how == "ASC":
        # Expected order (ASC):
        # 1. beta (5 hosts)
        # 2-4. alpha, gamma, zebra (10 hosts each, alphabetically ordered)
        assert results[0]["name"] == "beta_group" and results[0]["host_count"] == 5
        assert results[1]["name"] == "alpha_group" and results[1]["host_count"] == 10
        assert results[2]["name"] == "gamma_group" and results[2]["host_count"] == 10
        assert results[3]["name"] == "zebra_group" and results[3]["host_count"] == 10
    else:  # DESC
        # Expected order (DESC):
        # 1-3. alpha, gamma, zebra (10 hosts each, alphabetically ordered)
        # 4. beta (5 hosts)
        assert results[0]["name"] == "alpha_group" and results[0]["host_count"] == 10
        assert results[1]["name"] == "gamma_group" and results[1]["host_count"] == 10
        assert results[2]["name"] == "zebra_group" and results[2]["host_count"] == 10
        assert results[3]["name"] == "beta_group" and results[3]["host_count"] == 5


def test_get_groups_rbac_v2_ordering_by_host_count_too_many_groups(mocker, api_get):
    """
    Test GET /groups with RBAC v2, order_by=host_count when org has >3000 groups.

    NEGATIVE TEST: Verifies that ordering by host_count returns 400 error when
    there are too many groups to sort efficiently.

    Rationale: RBAC v2 can return max 3000 groups. We can't sort by host_count
    without fetching ALL groups and adding host counts from DB. With >3000 groups,
    we can't guarantee correct ordering. Better to return clear error asking user
    to use filters to narrow results.
    """
    # Mock feature flag enabled
    mocker.patch("api.group.get_flag_value", return_value=True)

    # Mock RBAC v2 returning 3500 total groups (exceeds MAX_GROUPS_FOR_HOST_COUNT_SORTING of 3000)
    # RBAC v2 returns first 3000 groups, but total=3500
    mock_workspaces = [
        _create_mock_workspace(name=f"group_{i}", workspace_id=str(generate_uuid()))
        for i in range(3000)  # Returns 3000 groups
    ]

    mock_get_rbac_workspaces = mocker.patch("api.group.get_rbac_workspaces")
    mock_get_rbac_workspaces.return_value = (mock_workspaces, 3500)  # total=3500 (>3000)

    # Request order_by=host_count with too many groups
    query = "?order_by=host_count"
    response_status, response_data = api_get(build_groups_url(query=query))

    # Should return 400 error with helpful message
    assert_response_status(response_status, 400)
    assert "3500" in response_data["detail"]  # Mentions actual total
    assert "3000" in response_data["detail"]  # Mentions the limit
    assert "filter" in response_data["detail"].lower()  # Suggests using filters
    assert "host_count" in response_data["detail"].lower()  # Mentions the problematic ordering field


def test_get_groups_rbac_v2_ordering_by_host_count_timeout(mocker, api_get):
    """
    Test 503 error when RBAC v2 times out during host_count sorting.

    NEGATIVE TEST: Verifies that RBAC v2 timeouts are handled gracefully
    even when using the special host_count sorting code path.
    """
    # Mock feature flag enabled
    mocker.patch("api.group.get_flag_value", return_value=True)

    # Mock get_rbac_workspaces to raise Timeout exception
    mock_get_rbac_workspaces = mocker.patch("api.group.get_rbac_workspaces")
    mock_get_rbac_workspaces.side_effect = Timeout("RBAC v2 API timed out")

    # Request order_by=host_count which triggers special code path
    query = "?order_by=host_count"
    response_status, response_data = api_get(build_groups_url(query=query))

    # Should return 503 (service unavailable)
    assert_response_status(response_status, 503)
    assert "RBAC service unavailable" in response_data["detail"] or "timed out" in response_data["detail"].lower()


def test_get_groups_rbac_v2_ordering_by_host_count_db_error(mocker, api_get):
    """
    Test error handling when database fails during host count fetching.

    NEGATIVE TEST: Verifies that database errors during serialize_group()
    (which fetches host counts) are handled properly.
    """
    # Mock feature flag enabled
    mocker.patch("api.group.get_flag_value", return_value=True)

    # Mock RBAC v2 returning valid workspaces
    mock_workspaces = [
        _create_mock_workspace(name="group_a", workspace_id=str(generate_uuid())),
        _create_mock_workspace(name="group_b", workspace_id=str(generate_uuid())),
    ]
    mock_get_rbac_workspaces = mocker.patch("api.group.get_rbac_workspaces")
    mock_get_rbac_workspaces.return_value = (mock_workspaces, 2)

    # Mock get_host_counts_batch to raise database error when fetching host counts
    mock_get_host_counts = mocker.patch("api.group.get_host_counts_batch")
    mock_get_host_counts.side_effect = OperationalError("Database connection failed", None, None)

    # Request order_by=host_count
    query = "?order_by=host_count"
    response_status, response_data = api_get(build_groups_url(query=query))

    # Should return 500 (internal server error) - database errors aren't caught in this path
    # This is expected behavior - database failures should bubble up
    assert_response_status(response_status, 500)


def test_get_groups_rbac_v2_ordering_by_host_count_all_empty_groups(mocker, api_get):
    """
    Test ordering by host_count when all groups have 0 hosts.

    EDGE CASE: Verifies that sorting still works when all host_counts are equal (0).
    Python's sort should provide stable ordering (preserves original order for equal values).
    """
    # Mock feature flag enabled
    mocker.patch("api.group.get_flag_value", return_value=True)

    # Mock RBAC v2 returning 3 workspaces in specific order
    mock_workspaces = [
        _create_mock_workspace(name="zebra_group", workspace_id=str(generate_uuid())),
        _create_mock_workspace(name="alpha_group", workspace_id=str(generate_uuid())),
        _create_mock_workspace(name="beta_group", workspace_id=str(generate_uuid())),
    ]

    mock_get_rbac_workspaces = mocker.patch("api.group.get_rbac_workspaces")
    mock_get_rbac_workspaces.return_value = (mock_workspaces, 3)

    # Mock all groups having 0 hosts
    def mock_get_host_count(_group_id, _org_id):
        return 0  # All groups empty

    mocker.patch(
        "lib.group_repository.get_host_counts_batch",
        side_effect=lambda org_id, group_ids: {gid: mock_get_host_count(gid, org_id) for gid in group_ids},
    )

    # Request order_by=host_count&order_how=ASC
    query = "?order_by=host_count&order_how=ASC"
    response_status, response_data = api_get(build_groups_url(query=query))

    # Should return 200 with all groups
    assert_response_status(response_status, 200)
    assert response_data["total"] == 3
    assert response_data["count"] == 3

    # All groups should have host_count=0
    results = response_data["results"]
    assert len(results) == 3
    assert all(group["host_count"] == 0 for group in results)

    # When host_counts are equal, groups should be ordered alphabetically by name (secondary sort)
    assert results[0]["name"] == "alpha_group"  # Alphabetically first
    assert results[1]["name"] == "beta_group"  # Alphabetically second
    assert results[2]["name"] == "zebra_group"  # Alphabetically third


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
def test_get_groups_rbac_v2_with_rbac_permissions(mocker, api_get):
    """
    Test GET /groups with RBAC v2 permissions.
    Verifies that RBAC v2 API returns only authorized workspaces based on identity header.

    Note: With RBAC v2, the workspace API filters results server-side using the
    identity header. Client-side RBAC v1 filtering is NOT applied because it would
    be redundant - RBAC v2 already knows what the user can access.
    """
    # Mock feature flag enabled
    mocker.patch("api.group.get_flag_value", return_value=True)

    # Mock RBAC permissions (RBAC v1 still runs for backward compatibility during migration)
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

    # Mock get_rbac_workspaces - RBAC v2 API returns only authorized workspaces
    # (filtered server-side based on identity header)
    mock_workspaces = [
        _create_mock_workspace(workspace_id=group_id_1, name="group1"),
        _create_mock_workspace(workspace_id=group_id_2, name="group2"),
    ]
    mock_get_rbac_workspaces = mocker.patch("api.group.get_rbac_workspaces")
    mock_get_rbac_workspaces.return_value = (mock_workspaces, 2)

    response_status, response_data = api_get(build_groups_url())

    assert_response_status(response_status, 200)
    assert response_data["total"] == 2

    # Verify get_rbac_workspaces was called (without rbac_filter - RBAC v2 handles filtering)
    assert mock_get_rbac_workspaces.called
    call_args = mock_get_rbac_workspaces.call_args
    # Verify rbac_filter is NOT passed (RBAC v2 filters server-side)
    # Parameters: name, page, per_page, group_type, order_by, order_how
    assert len(call_args[0]) == 6  # 6 positional args, no rbac_filter


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

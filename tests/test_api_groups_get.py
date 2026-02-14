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


def test_get_groups_by_id_rbac_v2_success(
    mocker, db_create_group, db_create_host, db_create_host_group_assoc, api_get
):
    """
    Test that GET /groups/{group_id_list} uses RBAC v2 when feature flag is enabled.

    JIRA: RHINENG-17397
    """
    # Create groups with hosts
    groups = [db_create_group(f"group_{i}") for i in range(3)]
    group_id_list = [str(group.id) for group in groups]

    # Add hosts to groups for host count verification
    for i, group in enumerate(groups):
        for _ in range(i + 1):  # group_0 has 1 host, group_1 has 2 hosts, group_2 has 3 hosts
            host = db_create_host()
            db_create_host_group_assoc(host.id, group.id)

    # Mock workspaces response from RBAC v2 API
    mock_workspaces = [
        {
            "id": str(group.id),
            "name": group.name,
            "org_id": "12345",
            "type": "standard",
            "created": "2025-11-06T20:40:41.151481Z",
            "modified": "2025-11-06T20:40:41.160109Z",
        }
        for group in groups
    ]

    # Mock feature flag enabled (RBAC v2 path)
    mock_config = mocker.patch("api.group.inventory_config")
    mock_config.return_value.bypass_kessel = False
    mocker.patch("api.group.get_flag_value", return_value=True)

    # Mock RBAC v2 workspace fetch
    mocker.patch("api.group.get_rbac_workspaces_by_ids", return_value=mock_workspaces)

    # Call endpoint
    response_status, response_data = api_get(GROUP_URL + "/" + ",".join(group_id_list))

    # Verify success
    assert_response_status(response_status, 200)
    assert response_data["total"] == 3
    assert response_data["count"] == 3
    assert len(response_data["results"]) == 3

    # Verify each group has correct data
    for i, group_result in enumerate(response_data["results"]):
        assert group_result["id"] == group_id_list[i]
        assert group_result["name"] == f"group_{i}"
        assert group_result["host_count"] == i + 1
        assert "created" in group_result
        assert "updated" in group_result


def test_get_groups_by_id_rbac_v2_not_found(mocker, db_create_group, api_get):
    """
    Test that GET /groups/{group_id_list} returns 404 when RBAC v2 workspace not found.

    JIRA: RHINENG-17397
    """
    # Create groups in database
    groups = [db_create_group(f"group_{i}") for i in range(3)]
    group_id_list = [str(group.id) for group in groups]

    # Mock feature flag enabled (RBAC v2 path)
    mock_config = mocker.patch("api.group.inventory_config")
    mock_config.return_value.bypass_kessel = False
    mocker.patch("api.group.get_flag_value", return_value=True)

    # Mock RBAC v2 workspace fetch to raise ResourceNotFoundException
    from app.exceptions import ResourceNotFoundException

    mocker.patch(
        "api.group.get_rbac_workspaces_by_ids",
        side_effect=ResourceNotFoundException("Workspaces not found: " + group_id_list[1]),
    )

    # Call endpoint
    response_status, response_data = api_get(GROUP_URL + "/" + ",".join(group_id_list))

    # Verify 404 error
    assert_response_status(response_status, 404)
    assert "One or more groups not found" in response_data["detail"]


def test_get_groups_by_id_rbac_v2_partial_not_found(mocker, db_create_group, api_get):
    """
    Test that GET /groups/{group_id_list} returns 404 when some workspaces are missing.

    JIRA: RHINENG-17397
    """
    # Create groups
    groups = [db_create_group(f"group_{i}") for i in range(3)]
    group_id_list = [str(group.id) for group in groups]

    # Mock feature flag enabled (RBAC v2 path)
    mock_config = mocker.patch("api.group.inventory_config")
    mock_config.return_value.bypass_kessel = False
    mocker.patch("api.group.get_flag_value", return_value=True)

    # Mock RBAC v2 workspace fetch to raise exception for partial results
    from app.exceptions import ResourceNotFoundException

    mocker.patch(
        "api.group.get_rbac_workspaces_by_ids",
        side_effect=ResourceNotFoundException(f"Workspaces not found: {group_id_list[2]}"),
    )

    # Call endpoint
    response_status, response_data = api_get(GROUP_URL + "/" + ",".join(group_id_list))

    # Verify 404 error
    assert_response_status(response_status, 404)
    assert "One or more groups not found" in response_data["detail"]


def test_get_groups_by_id_feature_flag_disabled(
    mocker, db_create_group, db_create_host, db_create_host_group_assoc, api_get
):
    """
    Test that GET /groups/{group_id_list} uses database when feature flag is disabled (RBAC v1).

    JIRA: RHINENG-17397
    """
    # Create groups with hosts
    groups = [db_create_group(f"group_{i}") for i in range(2)]
    group_id_list = [str(group.id) for group in groups]

    # Add hosts to groups
    for group in groups:
        host = db_create_host()
        db_create_host_group_assoc(host.id, group.id)

    # Mock feature flag disabled (RBAC v1 path - default behavior)
    mocker.patch("api.group.get_flag_value", return_value=False)

    # Call endpoint
    response_status, response_data = api_get(GROUP_URL + "/" + ",".join(group_id_list))

    # Verify success using database path
    assert_response_status(response_status, 200)
    assert response_data["total"] == 2
    assert response_data["count"] == 2
    assert len(response_data["results"]) == 2

    # Verify each group has correct data from database
    for i, group_result in enumerate(response_data["results"]):
        assert group_result["id"] == group_id_list[i]
        assert group_result["name"] == f"group_{i}"
        assert group_result["host_count"] == 1

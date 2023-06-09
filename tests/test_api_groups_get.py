import pytest

from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_groups_url
from tests.helpers.api_utils import GROUP_URL
from tests.helpers.test_utils import generate_uuid


def test_basic_group_query(db_create_group, api_get):
    group_id_list = [str(db_create_group(f"testGroup_{idx}").id) for idx in range(3)]

    response_status, response_data = api_get(build_groups_url())

    assert_response_status(response_status, 200)
    assert response_data["total"] == 3
    assert response_data["count"] == 3
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
def test_sort_by_host_ids(db_create_group_with_hosts, api_get, db_get_group_by_id, order_how_query, reverse_list):
    num_groups = 5

    # Create a list of groups. The names are randomized, but each group has one more host than the previous.
    group_id_list = [str(db_create_group_with_hosts(f"group{generate_uuid()}", idx).id) for idx in range(num_groups)]

    # If ordering in descending order, we expect the groups in reverse order.
    if reverse_list:
        group_id_list.reverse()

    query = f"?order_by=host_ids{order_how_query}"
    response_status, response_data = api_get(build_groups_url(query=query))

    assert_response_status(response_status, 200)
    assert response_data["total"] == num_groups
    assert response_data["count"] == num_groups
    for idx in range(num_groups):
        group_data = response_data["results"][idx]
        assert group_data["id"] == group_id_list[idx]
        assert group_data["host_count"] == len(db_get_group_by_id(group_id_list[idx]).hosts)


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

    response_status, response_data = api_get(GROUP_URL + "/" + generate_uuid())

    assert response_status == 200
    assert response_data["total"] == 0
    assert response_data["count"] == 0
    assert len(response_data["results"]) == 0


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
                    assert response_data["results"][idx]["name"] == f"testGroup_{((page-1)*per_page + idx):03}"


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
def test_sort_by_host_ids_with_pagination(
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
                query = f"?page={page}&per_page={per_page}&order_by=host_ids{order_how_query}"
                response_status, response_data = api_get(build_groups_url(query=query))
                assert response_status == 200
                assert response_data["total"] == len(group_id_list)
                assert response_data["count"] == per_page
                assert len(response_data["results"]) == per_page
                res = [d["id"] for d in response_data["results"]]  # Get only the ids from the results array
                assert res == group_id_list[start:end]  # compare the ids with the group_id_list
                start = end
                end = end + per_page

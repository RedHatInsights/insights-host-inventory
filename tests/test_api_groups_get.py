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


def test_query_variables_group_name(db_create_group, api_get):
    group_id = db_create_group("testGroup").id
    query = "?name=testGroup"

    response_status, response_data = api_get(build_groups_url(query=query))

    assert_response_status(response_status, 200)
    assert response_data["total"] == 1
    assert response_data["count"] == 1
    assert response_data["results"][0]["id"] == str(group_id)


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

import pytest

from tests.helpers.api_utils import assert_resource_types_pagination
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import build_resource_types_groups_url
from tests.helpers.api_utils import build_resource_types_url


@pytest.mark.parametrize(
    "num_groups",
    [0, 1, 10],
)
def test_basic_resource_types_query(api_get, db_create_group, num_groups):
    for idx in range(num_groups):
        db_create_group(f"testGroup_{idx}")

    response_status, response_data = api_get(build_resource_types_url())

    assert response_data["data"][0]["count"] == num_groups
    assert_response_status(response_status, 200)
    assert_resource_types_pagination(response_data, 1, 10, 1, "/inventory/v1/resource-types")


def test_resource_types_groups_data(api_get, db_create_group):
    # Create a few groups, then check that the data is correct in the response
    group_id_list = [str(db_create_group(f"testGroup{idx}").id) for idx in range(5)]

    response_status, response_data = api_get(build_resource_types_groups_url())

    assert_response_status(response_status, 200)

    for group_result in response_data["data"]:
        assert group_result["id"] in group_id_list

    assert_resource_types_pagination(response_data, 1, 10, 1, "/inventory/v1/resource-types/inventory-groups")


def test_resource_types_groups_pagination(api_get, db_create_group, subtests):
    # Create a bunch of groups, then use subtests to validate output with different pagination params
    num_groups = 40
    for idx in range(num_groups):
        # Use leading zeros so that we can sort by name
        db_create_group(f"testGroup_{idx:03}")

    for per_page in [1, 5, 10]:
        for page in [1, 2, 3]:
            with subtests.test():
                query = f"?page={page}&per_page={per_page}"
                response_status, response_data = response_status, response_data = api_get(
                    build_resource_types_groups_url(query=query)
                )

                assert_response_status(response_status, 200)
                assert_resource_types_pagination(
                    response_data,
                    page,
                    per_page,
                    int(num_groups / per_page),
                    "/inventory/v1/resource-types/inventory-groups",
                )

                for idx in range(per_page):
                    assert response_data["data"][idx]["name"] == f"testGroup_{((page-1)*per_page + idx):03}"

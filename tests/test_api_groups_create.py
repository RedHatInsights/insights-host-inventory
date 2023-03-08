import pytest

from tests.helpers.api_utils import assert_group_response
from tests.helpers.api_utils import assert_response_status


def test_create_group_without_hosts(api_create_group, db_get_group_by_name):
    group_data = {"name": "my_awesome_group"}

    response_status, response_data = api_create_group(group_data)

    assert_response_status(response_status, expected_status=201)

    retrieved_group = db_get_group_by_name(group_data.get("name"))
    assert_group_response(response_data, retrieved_group)


def test_create_group_with_hosts(db_create_host, api_create_group, db_get_group_by_name):
    host1 = db_create_host()
    host2 = db_create_host()
    host_id_list = [str(host1.id), str(host2.id)]

    group_data = {"name": "my_awesome_group", "host_ids": host_id_list}

    response_status, response_data = api_create_group(group_data)

    assert_response_status(response_status, expected_status=201)

    retrieved_group = db_get_group_by_name(group_data["name"])
    assert_group_response(response_data, retrieved_group)


def test_create_invalid_group_name(api_create_group):
    group_data = {"name": "", "host_ids": []}

    response_status, _ = api_create_group(group_data)

    assert_response_status(response_status, expected_status=406)


@pytest.mark.parametrize(
    "host_ids",
    [["", "3578"], ["notauuid"]],
)
def test_create_group_invalid_host_ids(api_create_group, host_ids):
    group_data = {"name": "my_awesome_group", "host_ids": host_ids}

    response_status, _ = api_create_group(group_data)

    assert_response_status(response_status, expected_status=400)

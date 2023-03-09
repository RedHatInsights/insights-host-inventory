from copy import deepcopy

import pytest

from tests.helpers.api_utils import assert_group_response
from tests.helpers.api_utils import assert_response_status
from tests.helpers.test_utils import SYSTEM_IDENTITY


def test_create_group_without_hosts(api_create_group, db_get_group_by_name):
    group_data = {"name": "my_awesome_group", "host_ids": []}

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


def test_create_group_invalid_name(api_create_group):
    group_data = {"name": "", "host_ids": []}

    response_status, _ = api_create_group(group_data)

    assert_response_status(response_status, expected_status=400)


def test_create_group_null_name(api_create_group):
    group_data = {"host_ids": []}

    response_status, response_data = api_create_group(group_data)

    assert_response_status(response_status, expected_status=400)
    assert "Group name cannot be null" in response_data["detail"]


def test_create_group_taken_name(api_create_group):
    group_data = {"name": "test_group", "host_ids": []}

    response_status, _ = api_create_group(group_data)
    response_status, response_data = api_create_group(group_data)

    assert_response_status(response_status, expected_status=400)
    assert group_data["name"] in response_data["detail"]


@pytest.mark.parametrize(
    "host_ids",
    [["", "3578"], ["notauuid"]],
)
def test_create_group_invalid_host_ids(api_create_group, host_ids):
    group_data = {"name": "my_awesome_group", "host_ids": host_ids}

    response_status, response_data = api_create_group(group_data)

    assert_response_status(response_status, expected_status=400)
    assert any(s in response_data["detail"] for s in host_ids)


def test_create_group_with_host_from_another_group(db_create_group_with_hosts, api_create_group):
    # Create a group with 2 hosts
    group = db_create_group_with_hosts("test_group", 2)
    assert len(group.hosts) == 2

    # Make an identity with a different org_id and account
    diff_identity = deepcopy(SYSTEM_IDENTITY)
    diff_identity["org_id"] = "diff_id"
    diff_identity["account"] = "diff_id"

    taken_host_id = str(group.hosts[0].id)

    group_data = {"name": "test_group_2", "host_ids": [taken_host_id]}

    response_status, response_body = api_create_group(group_data, identity=diff_identity)

    assert_response_status(response_status, 400)
    assert taken_host_id in response_body["detail"]


def test_create_group_with_host_from_another_org(db_create_host, api_create_group):
    host = db_create_host()
    host_id = str(host.id)

    # Make an identity with a different org_id and account
    diff_identity = deepcopy(SYSTEM_IDENTITY)
    diff_identity["org_id"] = "diff_id"
    diff_identity["account"] = "diff_id"

    group_data = {"name": "test_group_2", "host_ids": [host_id]}

    response_status, response_body = api_create_group(group_data, identity=diff_identity)

    assert_response_status(response_status, 400)
    assert host_id in response_body["detail"]

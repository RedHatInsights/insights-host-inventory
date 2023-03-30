from copy import deepcopy

import pytest

from tests.helpers.api_utils import assert_group_response
from tests.helpers.api_utils import assert_response_status
from tests.helpers.test_utils import SYSTEM_IDENTITY


@pytest.mark.parametrize(
    "num_hosts",
    [0, 3, 5],
)
@pytest.mark.parametrize("patch_name", [True, False])
def test_patch_group_happy_path(
    db_create_group, db_create_host, api_patch_group, db_get_group_by_id, num_hosts, patch_name
):
    group_id = db_create_group("test_group").id
    assert len(db_get_group_by_id(group_id).hosts) == 0

    host_id_list = [str(db_create_host().id)]

    patch_doc = {"host_ids": host_id_list}
    if patch_name:
        patch_doc["name"] = "modified_group"

    response_status, response_data = api_patch_group(group_id, patch_doc)
    assert_response_status(response_status, 200)
    retrieved_group = db_get_group_by_id(group_id)

    if patch_name:
        assert retrieved_group.name == "modified_group"
    else:
        assert retrieved_group.name == "test_group"

    assert str(retrieved_group.hosts[0].id) == host_id_list[0]

    # Patch again with different hosts and re-validate
    host_id_list = [str(db_create_host().id) for _ in range(num_hosts)]

    patch_doc = {"host_ids": host_id_list}
    if patch_name:
        patch_doc["name"] = "modified_again"

    response_status, response_data = api_patch_group(group_id, patch_doc)
    assert_response_status(response_status, 200)
    assert_group_response(response_data, db_get_group_by_id(group_id))
    retrieved_group = db_get_group_by_id(group_id)

    if patch_name:
        assert retrieved_group.name == "modified_again"
    else:
        assert retrieved_group.name == "test_group"

    assert [str(host.id) for host in retrieved_group.hosts] == host_id_list

    assert_response_status(response_status, 200)


def test_patch_group_wrong_org_id_for_group(db_create_group_with_hosts, db_create_host, api_patch_group):
    # Create a group with 2 hosts
    group = db_create_group_with_hosts("test_group", 2)
    assert len(group.hosts) == 2

    # Make an identity with a different org_id and account
    diff_identity = deepcopy(SYSTEM_IDENTITY)
    diff_identity["org_id"] = "diff_id"
    diff_identity["account"] = "diff_id"

    host_id_list = [str(db_create_host().id) for _ in range(5)]

    patch_doc = {"name": "modified_group", "host_ids": host_id_list}

    response_status, response_data = api_patch_group(group.id, patch_doc, diff_identity)

    # It can't find a group with that ID within the user's org, so it should return 404
    assert_response_status(response_status, 404)


def test_patch_group_existing_name_different_org(db_create_group_with_hosts, db_create_host, api_patch_group):
    # Create a group with 2 hosts
    group = db_create_group_with_hosts("test_group", 2)
    assert len(group.hosts) == 2

    # Make an identity with a different org_id and account
    diff_identity = deepcopy(SYSTEM_IDENTITY)
    diff_identity["org_id"] = "diff_id"
    diff_identity["account"] = "diff_id"

    host_id_list = [str(db_create_host().id) for _ in range(5)]

    patch_doc = {"name": "modified_group", "host_ids": host_id_list}

    response_status, response_data = api_patch_group(group.id, patch_doc, diff_identity)

    # It can't find a group with that ID within the user's org, so it should return 404
    assert_response_status(response_status, 404)


@pytest.mark.parametrize("patch_name", ["existing_group", "EXISTING_GROUP"])
def test_patch_group_existing_name_same_org(db_create_group, api_patch_group, patch_name):
    # Create 2 groups
    db_create_group("existing_group").id
    new_id = db_create_group("another_group").id

    response_status, response_body = api_patch_group(new_id, {"name": patch_name})

    # There's already a group with that name (case-insensitive), so we should get an HTTP 400.
    # Make sure the group name is mentioned in the response.
    assert_response_status(response_status, 400)
    assert patch_name in response_body["detail"]


def test_patch_group_hosts_from_different_group(db_create_group_with_hosts, api_patch_group):
    # Create 2 groups
    host_to_move_id = str(db_create_group_with_hosts("existing_group", 3).hosts[0].id)
    new_id = db_create_group_with_hosts("new_group", 1).id

    patch_doc = {"host_ids": [host_to_move_id]}

    response_status, response_body = api_patch_group(new_id, patch_doc)

    # There's already a group with that name, so we should get an HTTP 400.
    # Make sure the host ID at fault is mentioned in the response.
    assert_response_status(response_status, 400)
    assert str(host_to_move_id) in response_body["detail"]


def test_patch_group_no_name(db_create_group_with_hosts, api_patch_group, db_get_group_by_id):
    group = db_create_group_with_hosts("test_group", 2)
    patch_doc = {"name": ""}

    response_status, _ = api_patch_group(group.id, patch_doc)

    # The group name isn't allowed to be empty, so return 400
    assert_response_status(response_status, 400)

    # Assert that the group's name hasn't been modified
    assert db_get_group_by_id(group.id).name == "test_group"

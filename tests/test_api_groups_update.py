from copy import deepcopy

import pytest

from tests.helpers.api_utils import assert_group_response
from tests.helpers.api_utils import assert_response_status
from tests.helpers.test_utils import SYSTEM_IDENTITY


@pytest.mark.parametrize(
    "num_hosts",
    [1, 3, 5],
)
def test_patch_group_happy_path(db_create_group, db_create_host, api_patch_group, db_get_group, num_hosts):
    group_id = db_create_group("test_group").id
    assert len(db_get_group(group_id).hosts) == 0

    host_id_list = [str(db_create_host().id)]

    patch_doc = {"name": "modified_group", "host_ids": host_id_list}

    response_status, response_data = api_patch_group(group_id, patch_doc)
    assert_response_status(response_status, 200)
    retrieved_group = db_get_group(group_id)
    assert retrieved_group.name == "modified_group"
    assert str(retrieved_group.hosts[0].id) == host_id_list[0]

    # Patch again with different hosts and re-validate
    host_id_list = [str(db_create_host().id) for _ in range(num_hosts)]

    patch_doc = {"name": "modified_again", "host_ids": host_id_list}

    response_status, response_data = api_patch_group(group_id, patch_doc)
    assert_response_status(response_status, 200)
    assert_group_response(response_data, db_get_group(group_id))
    retrieved_group = db_get_group(group_id)
    assert retrieved_group.name == "modified_again"
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


def test_patch_group_existing_name_same_org(db_create_group_with_hosts, db_create_host, api_patch_group):
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


def test_patch_group_no_name(db_create_group_with_hosts, api_patch_group, db_get_group):
    group = db_create_group_with_hosts("test_group", 2)
    patch_doc = {"name": ""}

    response_status, _ = api_patch_group(group.id, patch_doc)

    # The group name isn't allowed to be empty, so return 400
    assert_response_status(response_status, 400)

    # Assert that the group's name hasn't been modified
    assert db_get_group(group.id).name == "test_group"

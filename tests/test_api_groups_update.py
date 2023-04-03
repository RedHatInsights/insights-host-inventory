from copy import deepcopy

import pytest
from dateutil import parser

from tests.helpers.api_utils import assert_group_response
from tests.helpers.api_utils import assert_response_status
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import SYSTEM_IDENTITY


@pytest.mark.parametrize(
    "num_hosts",
    [0, 3, 5],
)
@pytest.mark.parametrize("patch_name", [True, False])
def test_patch_group_happy_path(
    db_create_group, db_create_host, db_get_group_by_id, api_patch_group, num_hosts, patch_name
):
    group = db_create_group("test_group")
    group_id = group.id
    orig_modified_on = group.modified_on
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
    # Assert that the modified_on date has been updated
    assert retrieved_group.modified_on > orig_modified_on

    # Confirm that the updated date on the json data matches the date in the DB
    assert parser.isoparse(response_data["updated"]) == retrieved_group.modified_on


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


@pytest.mark.parametrize("host_in_other_org", [True, False])
def test_patch_group_hosts_in_diff_org(
    db_create_group_with_hosts, api_patch_group, db_create_host, db_get_group_by_id, host_in_other_org
):
    # Create a group
    group = db_create_group_with_hosts("test_group", 2)
    orig_modified_on = group.modified_on
    group_id = group.id

    # Make an identity with a different org_id and account
    diff_identity = deepcopy(SYSTEM_IDENTITY)
    diff_identity["org_id"] = "diff_id"
    diff_identity["account"] = "diff_id"

    # Create 3 hosts in the same org
    host_id_list = [str(db_create_host().id) for _ in range(3)]

    if host_in_other_org:
        # Create one host in a different org
        invalid_host_id = db_create_host(identity=diff_identity).id
    else:
        # Append a UUID not associated with any host
        invalid_host_id = generate_uuid()

    host_id_list.append(str(invalid_host_id))
    patch_doc = {"host_ids": host_id_list}

    response_status, response_data = api_patch_group(group_id, patch_doc)

    # It can't find that host in the current org
    assert_response_status(response_status, 400)
    assert response_data["detail"] == f"Host with ID {invalid_host_id} does not exist."
    retrieved_group = db_get_group_by_id(group_id)

    # There should still only be 2 hosts on the group
    assert len(retrieved_group.hosts) == 2

    # The group
    assert db_get_group_by_id(group_id).modified_on == orig_modified_on

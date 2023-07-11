import json
from copy import deepcopy

import pytest
from dateutil import parser

from tests.helpers.api_utils import assert_group_response
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import create_mock_rbac_response
from tests.helpers.test_utils import generate_uuid
from tests.helpers.test_utils import SYSTEM_IDENTITY


@pytest.mark.parametrize(
    "num_hosts",
    [0, 3, 5],
)
@pytest.mark.parametrize("patch_name", [True, False])
def test_patch_group_happy_path(
    db_create_group,
    db_create_host,
    db_get_group_by_id,
    db_get_hosts_for_group,
    api_patch_group,
    num_hosts,
    patch_name,
    event_producer,
    mocker,
):
    # Create a group with no hosts
    mocker.patch.object(event_producer, "write_event")
    group = db_create_group("test_group")
    group_id = group.id
    orig_modified_on = group.modified_on
    assert len(db_get_hosts_for_group(group_id)) == 0

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

    assert str(db_get_hosts_for_group(group_id)[0].id) == host_id_list[0]
    assert event_producer.write_event.call_count == 1

    # Patch again with different hosts and re-validate
    event_producer.write_event.reset_mock()
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

    for host in db_get_hosts_for_group(group_id):
        assert str(host.id) in host_id_list

    assert_response_status(response_status, 200)
    # Assert that the modified_on date has been updated
    assert retrieved_group.modified_on > orig_modified_on

    # Confirm that the updated date on the json data matches the date in the DB
    assert parser.isoparse(response_data["updated"]) == retrieved_group.modified_on

    # Validate the event_producer's messages
    # Call count should be the num_hosts +1 since the first message is the existing host being removed
    assert event_producer.write_event.call_count == num_hosts + 1
    for call_arg in event_producer.write_event.call_args_list[1:]:
        host = json.loads(call_arg[0][0])["host"]
        assert host["id"] in host_id_list
        assert host["groups"][0]["id"] == str(group_id)
        assert "host_count" not in host["groups"][0]


def test_patch_group_wrong_org_id_for_group(
    db_create_group_with_hosts, db_create_host, db_get_hosts_for_group, api_patch_group
):
    # Create a group with 2 hosts
    group = db_create_group_with_hosts("test_group", 2)
    assert len(db_get_hosts_for_group(group.id)) == 2

    # Make an identity with a different org_id and account
    diff_identity = deepcopy(SYSTEM_IDENTITY)
    diff_identity["org_id"] = "diff_id"
    diff_identity["account"] = "diff_id"

    host_id_list = [str(db_create_host().id) for _ in range(5)]

    patch_doc = {"name": "modified_group", "host_ids": host_id_list}

    response_status, response_data = api_patch_group(group.id, patch_doc, diff_identity)

    # It can't find a group with that ID within the user's org, so it should return 404
    assert_response_status(response_status, 404)


def test_patch_group_existing_name_different_org(
    db_create_group_with_hosts, db_create_host, db_get_hosts_for_group, api_patch_group
):
    # Create a group with 2 hosts
    group = db_create_group_with_hosts("test_group", 2)
    assert len(db_get_hosts_for_group(group.id)) == 2

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


def test_patch_group_hosts_from_different_group(
    db_create_group_with_hosts, api_patch_group, db_get_hosts_for_group, event_producer, mocker
):
    mocker.patch.object(event_producer, "write_event")
    # Create 2 groups
    group_id = db_create_group_with_hosts("existing_group", 3).id
    host_to_move_id = str(db_get_hosts_for_group(group_id)[0].id)
    new_id = db_create_group_with_hosts("new_group", 1).id

    patch_doc = {"host_ids": [host_to_move_id]}

    response_status, response_body = api_patch_group(new_id, patch_doc)

    # There's already a group with that name, so we should get an HTTP 400.
    # Make sure the host ID at fault is mentioned in the response.
    assert_response_status(response_status, 400)
    assert str(host_to_move_id) in response_body["detail"]

    # Make sure no events got produced
    assert event_producer.write_event.call_count == 0


def test_patch_groups_RBAC_allowed_specific_groups(
    mocker, db_create_group_with_hosts, api_patch_group, enable_rbac, event_producer
):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    group_id = str(db_create_group_with_hosts("new_group", 3).id)
    # Make a list of allowed group IDs (including some mock ones)
    group_id_list = [generate_uuid(), group_id, generate_uuid()]

    # Grant permissions to all 3 groups
    mock_rbac_response = create_mock_rbac_response(
        "tests/helpers/rbac-mock-data/inv-groups-write-resource-defs-template.json"
    )
    mock_rbac_response[0]["resourceDefinitions"][0]["attributeFilter"]["value"] = group_id_list

    get_rbac_permissions_mock.return_value = mock_rbac_response
    patch_doc = {"name": "new_name"}

    response_status, _ = api_patch_group(group_id, patch_doc)

    # Should be allowed
    assert_response_status(response_status, 200)


def test_patch_groups_RBAC_denied_specific_groups(mocker, db_create_group_with_hosts, api_patch_group, enable_rbac):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    group_id = str(db_create_group_with_hosts("new_group", 3).id)

    # Deny access to created group
    mock_rbac_response = create_mock_rbac_response(
        "tests/helpers/rbac-mock-data/inv-groups-write-resource-defs-template.json"
    )
    mock_rbac_response[0]["resourceDefinitions"][0]["attributeFilter"]["value"] = [generate_uuid(), generate_uuid()]
    get_rbac_permissions_mock.return_value = mock_rbac_response

    patch_doc = {"name": "new_name"}
    response_status, _ = api_patch_group(group_id, patch_doc)

    # Access was not granted
    assert_response_status(response_status, 403)


def test_patch_group_no_name(db_create_group_with_hosts, api_patch_group, db_get_group_by_id, event_producer, mocker):
    mocker.patch.object(event_producer, "write_event")
    group = db_create_group_with_hosts("test_group", 2)
    patch_doc = {"name": ""}

    response_status, _ = api_patch_group(group.id, patch_doc)

    # The group name isn't allowed to be empty, so return 400
    assert_response_status(response_status, 400)

    # Assert that the group's name hasn't been modified
    assert db_get_group_by_id(group.id).name == "test_group"

    # Make sure no events got produced
    assert event_producer.write_event.call_count == 0


@pytest.mark.parametrize("host_in_other_org", [True, False])
def test_patch_group_hosts_in_diff_org(
    db_create_group_with_hosts,
    api_patch_group,
    db_create_host,
    db_get_hosts_for_group,
    db_get_group_by_id,
    host_in_other_org,
    event_producer,
    mocker,
):
    mocker.patch.object(event_producer, "write_event")

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
    assert str(invalid_host_id) in response_data["detail"]

    # There should still only be 2 hosts on the group
    assert len(db_get_hosts_for_group(group_id)) == 2

    # The group
    assert db_get_group_by_id(group_id).modified_on == orig_modified_on

    # Make sure no events got produced
    assert event_producer.write_event.call_count == 0


def test_patch_group_name_only(
    db_create_group_with_hosts, db_get_group_by_id, db_get_hosts_for_group, api_patch_group, event_producer, mocker
):
    # Create a group with one host
    mocker.patch.object(event_producer, "write_event")
    group = db_create_group_with_hosts("test_group", 1)
    group_id = group.id
    orig_modified_on = group.modified_on

    host_id = str(db_get_hosts_for_group(group_id)[0].id)
    patch_doc = {"name": "modified_group"}

    response_status, response_data = api_patch_group(group_id, patch_doc)
    assert_response_status(response_status, 200)
    retrieved_group = db_get_group_by_id(group_id)

    assert retrieved_group.name == "modified_group"
    assert str(db_get_hosts_for_group(group_id)[0].id) == host_id
    assert retrieved_group.modified_on > orig_modified_on

    # Confirm that the updated date on the json data matches the date in the DB
    assert parser.isoparse(response_data["updated"]) == retrieved_group.modified_on

    # Validate the event_producer's message
    assert event_producer.write_event.call_count == 1
    host = json.loads(event_producer.write_event.call_args_list[0][0][0])["host"]
    assert host["id"] == host_id
    assert host["groups"][0]["id"] == str(group_id)
    assert host["groups"][0]["name"] == "modified_group"


def test_patch_group_same_hosts(
    db_create_group_with_hosts, db_get_group_by_id, api_patch_group, event_producer, mocker
):
    # Create a group with hosts
    mocker.patch.object(event_producer, "write_event")
    group = db_create_group_with_hosts("test_group", 5)
    group_id = group.id
    host_id_list = [str(host.id) for host in group.hosts]

    patch_doc = {"name": "modified_group", "host_ids": host_id_list}
    response_status, _ = api_patch_group(group_id, patch_doc)
    assert_response_status(response_status, 200)

    # Validate that we only sent 1 message per host
    assert event_producer.write_event.call_count == 5
    for call_arg in event_producer.write_event.call_args_list:
        host = json.loads(call_arg[0][0])["host"]
        assert host["id"] in host_id_list
        assert host["groups"][0]["id"] == str(group_id)


def test_patch_group_both_add_and_remove_hosts(
    db_create_group_with_hosts, db_get_group_by_id, db_create_host, api_patch_group, event_producer, mocker
):
    # Create a group with hosts
    mocker.patch.object(event_producer, "write_event")
    group = db_create_group_with_hosts("test_group", 3)
    group_id = group.id
    original_host_id_list = [str(host.id) for host in group.hosts]

    # Two hosts dropped, one host persists, two hosts added
    new_host_id_list = [original_host_id_list[0], str(db_create_host().id), str(db_create_host().id)]

    patch_doc = {"name": "modified_group", "host_ids": new_host_id_list}
    response_status, _ = api_patch_group(group_id, patch_doc)
    assert_response_status(response_status, 200)

    # We should have sent 5 messages:
    # 2 for the removed hosts, 1 for the persisting host, 2 for new hosts
    assert event_producer.write_event.call_count == 5
    for call_arg in event_producer.write_event.call_args_list:
        host = json.loads(call_arg[0][0])["host"]
        if host["id"] in new_host_id_list:
            assert host["id"] in new_host_id_list
            assert host["groups"][0]["id"] == str(group_id)
        else:
            assert host["groups"] == []

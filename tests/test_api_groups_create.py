import contextlib
import json
from copy import deepcopy

import pytest
from dateutil import parser
from sqlalchemy.exc import IntegrityError

from app.auth.identity import Identity
from app.auth.identity import to_auth_header
from tests.helpers.api_utils import GROUP_WRITE_PROHIBITED_RBAC_RESPONSE_FILES
from tests.helpers.api_utils import assert_group_response
from tests.helpers.api_utils import assert_response_status
from tests.helpers.api_utils import create_mock_rbac_response
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import generate_uuid


def test_create_group_with_empty_host_list(api_create_group, db_get_group_by_name, event_producer, mocker):
    mocker.patch.object(event_producer, "write_event")
    group_data = {"name": "my_awesome_group", "host_ids": []}

    response_status, response_data = api_create_group(group_data)

    assert_response_status(response_status, expected_status=201)

    retrieved_group = db_get_group_by_name(group_data.get("name"))
    assert_group_response(response_data, retrieved_group, 0)

    # No hosts modified, so no events should be written.
    assert event_producer.write_event.call_count == 0


def test_create_group_without_hosts_in_request_body(api_create_group, db_get_group_by_name, event_producer, mocker):
    mocker.patch.object(event_producer, "write_event")
    group_data = {"name": "my_awesome_group"}

    response_status, response_data = api_create_group(group_data)

    assert_response_status(response_status, expected_status=201)

    retrieved_group = db_get_group_by_name(group_data.get("name"))
    assert_group_response(response_data, retrieved_group, 0)

    # No hosts modified, so no events should be written.
    assert event_producer.write_event.call_count == 0


def test_create_group_with_hosts(
    db_create_host, api_create_group, db_get_group_by_name, db_get_host, mocker, event_producer
):
    mocker.patch.object(event_producer, "write_event")
    host1 = db_create_host()
    host2 = db_create_host()
    host_id_list = [str(host1.id), str(host2.id)]

    group_data = {"name": "my_awesome_group", "host_ids": host_id_list}

    response_status, response_data = api_create_group(group_data)

    assert_response_status(response_status, expected_status=201)

    retrieved_group = db_get_group_by_name(group_data["name"])
    assert_group_response(response_data, retrieved_group, 2)
    assert event_producer.write_event.call_count == 2
    for call_arg in event_producer.write_event.call_args_list:
        event = json.loads(call_arg[0][0])
        host = event["host"]
        assert host["id"] in host_id_list
        assert host["groups"][0]["name"] == group_data["name"]
        assert host["groups"][0]["id"] == str(retrieved_group.id)
        assert parser.isoparse(host["updated"]) == db_get_host(host["id"]).modified_on
        assert event["platform_metadata"] == {"b64_identity": to_auth_header(Identity(obj=USER_IDENTITY))}


@pytest.mark.parametrize(
    "new_name",
    [
        "",
        "  ",
    ],
)
def test_create_group_invalid_name(api_create_group, new_name):
    group_data = {"name": new_name, "host_ids": []}

    response_status, _ = api_create_group(group_data)

    assert_response_status(response_status, expected_status=400)


def test_create_group_null_name(api_create_group):
    group_data = {"host_ids": []}

    response_status, response_data = api_create_group(group_data)

    assert_response_status(response_status, expected_status=400)
    assert "Group name cannot be null" in response_data["detail"]


def test_create_group_read_only(api_create_group, mocker):
    group_data = {"name": "test", "host_ids": []}
    with mocker.patch("lib.middleware.get_flag_value", return_value=True):
        response_status, _ = api_create_group(group_data)
        assert_response_status(response_status, expected_status=503)


@pytest.mark.parametrize(
    "new_name",
    ["test_Group", " Test_Group", "test_group ", " test_group "],
)
def test_create_group_taken_name(api_create_group, new_name):
    group_data = {"name": "test_group", "host_ids": []}

    api_create_group(group_data)
    group_data["name"] = new_name
    response_status, _ = api_create_group(group_data)

    # Post-Kessel Phase 0, the group should be created successfully.
    assert_response_status(response_status, expected_status=201)


@pytest.mark.usefixtures("event_producer", "enable_kessel")
def test_create_group_taken_name_in_kessel_rbac(api_create_group):
    group_data = {"name": "test_group", "host_ids": []}

    error_message = "RBAC client error: Can't create workspace with same name within same parent workspace"
    response_status, response_data = api_create_group(group_data, abort_status=400, abort_detail=error_message)

    assert_response_status(response_status, expected_status=400)
    assert_response_status(response_data["detail"], error_message)


@pytest.mark.parametrize(
    "host_ids",
    [["", "3578"], ["notauuid"]],
)
def test_create_group_invalid_host_ids(api_create_group, host_ids, event_producer, mocker):
    mocker.patch.object(event_producer, "write_event")
    group_data = {"name": "my_awesome_group", "host_ids": host_ids}

    response_status, response_data = api_create_group(group_data)

    assert_response_status(response_status, expected_status=400)
    assert any(s in response_data["detail"] for s in host_ids)

    # No hosts modified, so no events should be written.
    assert event_producer.write_event.call_count == 0


@pytest.mark.parametrize(
    "host_ids",
    [[str(generate_uuid())] * 2, [str(generate_uuid())] + [str(generate_uuid())] * 2],
)
def test_create_group_duplicate_host_ids(api_create_group, db_create_host, host_ids, event_producer, mocker):
    mocker.patch.object(event_producer, "write_event")
    group_data = {"name": "my_awesome_group", "host_ids": host_ids}

    # Create hosts with the given host IDs, ignoring duplicates
    from uuid import UUID

    for host_id in host_ids:
        with contextlib.suppress(IntegrityError):
            db_create_host(extra_data={"id": UUID(host_id)})

    response_status, response_data = api_create_group(group_data)

    assert_response_status(response_status, expected_status=400)
    assert "Host IDs must be unique." in response_data["detail"]

    # No hosts modified, so no events should be written.
    assert event_producer.write_event.call_count == 0


def test_create_group_with_host_from_another_group(
    db_create_group_with_hosts, db_get_hosts_for_group, api_create_group, event_producer, mocker
):
    mocker.patch.object(event_producer, "write_event")
    # Create a group with 2 hosts
    group = db_create_group_with_hosts("test_group", 2)
    hosts_in_group = db_get_hosts_for_group(group.id)
    assert len(hosts_in_group) == 2

    # Make an identity with a different org_id and account
    diff_identity = deepcopy(SYSTEM_IDENTITY)
    diff_identity["org_id"] = "diff_id"
    diff_identity["account"] = "diff_id"

    taken_host_id = str(hosts_in_group[0].id)

    group_data = {"name": "test_group_2", "host_ids": [taken_host_id]}

    response_status, response_body = api_create_group(group_data, identity=diff_identity)

    assert_response_status(response_status, 400)
    assert taken_host_id in response_body["detail"]

    # No hosts modified, so no events should be written.
    assert event_producer.write_event.call_count == 0


def test_create_group_with_host_from_another_org(db_create_host, api_create_group, event_producer, mocker):
    mocker.patch.object(event_producer, "write_event")
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

    # No hosts modified, so no events should be written.
    assert event_producer.write_event.call_count == 0


@pytest.mark.usefixtures("enable_rbac")
def test_create_group_RBAC_denied(subtests, mocker, api_create_group, db_get_group_by_name):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")
    group_data = {"name": "my_awesome_group", "host_ids": []}

    for response_file in GROUP_WRITE_PROHIBITED_RBAC_RESPONSE_FILES:
        mock_rbac_response = create_mock_rbac_response(response_file)

        with subtests.test():
            get_rbac_permissions_mock.return_value = mock_rbac_response

            response_status, _ = api_create_group(group_data)

            assert_response_status(response_status, 403)

            assert not db_get_group_by_name("my_awesome_group")


@pytest.mark.usefixtures("enable_rbac")
def test_create_group_RBAC_denied_attribute_filter(mocker, api_create_group):
    get_rbac_permissions_mock = mocker.patch("lib.middleware.get_rbac_permissions")

    # Mock the RBAC response with a groups-write permission that has an attributeFilter
    mock_rbac_response = create_mock_rbac_response(
        "tests/helpers/rbac-mock-data/inv-groups-write-resource-defs-template.json"
    )
    mock_rbac_response[0]["resourceDefinitions"][0]["attributeFilter"]["value"] = [generate_uuid(), generate_uuid()]
    get_rbac_permissions_mock.return_value = mock_rbac_response

    group_data = {"name": "my_awesome_group", "host_ids": []}
    response_status, _ = api_create_group(group_data)

    # Access denied because of the attributeFilter
    assert_response_status(response_status, 403)


@pytest.mark.usefixtures("event_producer")
def test_create_group_same_name_kessel_phase1_enabled(api_create_group, db_get_group_by_name):
    """Test that groups with the same name can be created when FLAG_INVENTORY_KESSEL_PHASE_1 is True."""
    group_data = {"name": "duplicate_group_name", "host_ids": []}

    # Create the first group
    response_status, response_data = api_create_group(group_data)
    assert_response_status(response_status, expected_status=201)

    first_group = db_get_group_by_name(group_data["name"])
    assert first_group is not None
    assert_group_response(response_data, first_group, 0)

    # Create the second group with the same name - should succeed when Kessel Phase 1 is enabled
    response_status, response_data = api_create_group(group_data)
    assert_response_status(response_status, expected_status=201)

    # Verify the second group was created successfully
    # We can't use assert_group_response here since we can't easily retrieve the second group
    # with the same name, but we can verify the response structure
    assert "id" in response_data
    assert "name" in response_data
    assert response_data["name"] == group_data["name"]
    assert "host_count" in response_data
    assert response_data["host_count"] == 0

    # The successful 201 response indicates the second group was created
    # without the uniqueness constraint being enforced when Kessel Phase 1 is enabled


@pytest.mark.usefixtures("enable_kessel")
def test_create_group_skips_wait_when_group_already_exists(flask_client, db_create_group, mocker):
    """Test that wait_for_workspace_event is skipped if the group already exists in the database."""
    # Create a group directly in the database first
    existing_group = db_create_group("existing_group")
    workspace_id = str(existing_group.id)

    # Mock post_rbac_workspace to return the existing group's ID (simulating a race condition
    # where the MQ message was processed before we started listening)
    mocker.patch("api.group.post_rbac_workspace", return_value=workspace_id)
    mocker.patch("lib.group_repository.rbac_create_ungrouped_hosts_workspace", return_value=generate_uuid())

    # Mock wait_for_workspace_event to track if it's called
    wait_mock = mocker.patch("api.group.wait_for_workspace_event")

    group_data = {"name": "existing_group", "host_ids": []}
    response = flask_client.post(
        "/api/inventory/v1/groups",
        data=json.dumps(group_data),
        headers={"x-rh-identity": to_auth_header(Identity(obj=USER_IDENTITY)), "Content-Type": "application/json"},
    )

    assert response.status_code == 201
    # wait_for_workspace_event should NOT have been called since the group already exists
    wait_mock.assert_not_called()


@pytest.mark.usefixtures("enable_kessel")
def test_create_group_calls_wait_when_group_does_not_exist(flask_client, db_create_group, mocker):
    """Test that wait_for_workspace_event is called when the group doesn't exist yet."""
    # Create a group in the database that will be returned after wait_for_workspace_event
    existing_group = db_create_group("new_group")
    workspace_id = str(existing_group.id)

    # Mock post_rbac_workspace to return the workspace ID
    mocker.patch("api.group.post_rbac_workspace", return_value=workspace_id)
    mocker.patch("lib.group_repository.rbac_create_ungrouped_hosts_workspace", return_value=generate_uuid())

    # Mock wait_for_workspace_event to prevent actual waiting
    wait_mock = mocker.patch("api.group.wait_for_workspace_event")

    # Mock get_group_by_id_from_db to return None on first call (group doesn't exist yet).
    # Since wait_for_workspace_event doesn't raise TimeoutError, the second check in the
    # exception handler won't be called, so we only need to handle the first call.
    mocker.patch("api.group.get_group_by_id_from_db", side_effect=[None, existing_group, existing_group])

    group_data = {"name": "new_group", "host_ids": []}
    response = flask_client.post(
        "/api/inventory/v1/groups",
        data=json.dumps(group_data),
        headers={"x-rh-identity": to_auth_header(Identity(obj=USER_IDENTITY)), "Content-Type": "application/json"},
    )

    assert response.status_code == 201
    # wait_for_workspace_event SHOULD have been called since the group didn't exist on first check
    wait_mock.assert_called_once()


@pytest.mark.usefixtures("enable_kessel")
def test_create_group_succeeds_when_group_exists_after_timeout(flask_client, db_create_group, mocker):
    """Test that group creation succeeds if timeout occurs but group exists after second check.

    There is a slight window between getting the group and starting the wait when we still
    could have missed the event. This test verifies we check again after timeout to catch
    these instances.
    """
    # Create a group in the database
    existing_group = db_create_group("timeout_group")
    workspace_id = str(existing_group.id)

    # Mock post_rbac_workspace to return the workspace ID
    mocker.patch("api.group.post_rbac_workspace", return_value=workspace_id)
    mocker.patch("lib.group_repository.rbac_create_ungrouped_hosts_workspace", return_value=generate_uuid())

    # Mock wait_for_workspace_event to raise TimeoutError
    mocker.patch("api.group.wait_for_workspace_event", side_effect=TimeoutError)

    # Mock get_group_by_id_from_db:
    # - First call (check before wait): return None (group doesn't exist yet)
    # - Second call (check after timeout): return the real group from DB
    original_get_group = __import__(
        "lib.group_repository", fromlist=["get_group_by_id_from_db"]
    ).get_group_by_id_from_db
    call_count = {"count": 0}

    def mock_get_group(group_id, org_id, session=None):
        call_count["count"] += 1
        if call_count["count"] == 1:
            return None  # First call: group doesn't exist yet
        return original_get_group(group_id, org_id, session)  # Second call: return real group

    mocker.patch("api.group.get_group_by_id_from_db", side_effect=mock_get_group)

    group_data = {"name": "timeout_group", "host_ids": []}
    response = flask_client.post(
        "/api/inventory/v1/groups",
        data=json.dumps(group_data),
        headers={"x-rh-identity": to_auth_header(Identity(obj=USER_IDENTITY)), "Content-Type": "application/json"},
    )

    # Should succeed because group exists on the second check after timeout
    assert response.status_code == 201

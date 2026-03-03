import contextlib
import json
from collections.abc import Callable
from copy import deepcopy
from unittest.mock import MagicMock

import pytest
from dateutil import parser
from pytest_mock import MockerFixture
from sqlalchemy.exc import IntegrityError
from starlette.testclient import TestClient

from app.auth.identity import Identity
from app.auth.identity import to_auth_header
from app.config import Config
from app.models import Group
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


@pytest.fixture
def mock_pg_listen_connection(mocker: MockerFixture) -> MagicMock:
    """Fixture to mock the PostgreSQL LISTEN/NOTIFY connection used by wait_for_workspace_event."""
    mock_cursor = mocker.MagicMock()
    mock_conn = mocker.MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_conn.notifies = []

    # Mock raw_db_connection as imported in lib.group_repository
    mocker.patch("lib.group_repository.raw_db_connection", return_value=mock_conn)

    return mock_conn


@pytest.mark.usefixtures("enable_kessel", "event_producer")
def test_wait_for_workspace_event_returns_early_when_db_check_finds_group(
    flask_client: TestClient,
    db_create_group: Callable[..., Group],
    mocker: MockerFixture,
    mock_pg_listen_connection: MagicMock,
) -> None:
    """Test that wait_for_workspace_event returns early if the DB check finds the group.

    This tests the race condition handling: if the NOTIFY was sent before we started
    listening, the group already exists in the DB, and we return immediately.
    """
    # Create a group directly in the database first
    existing_group = db_create_group("existing_group")
    workspace_id = str(existing_group.id)

    # Mock post_rbac_workspace to return the existing group's ID
    mocker.patch("api.group.post_rbac_workspace", return_value=workspace_id)
    mocker.patch("lib.group_repository.rbac_create_ungrouped_hosts_workspace", return_value=generate_uuid())

    # The real get_group_by_id_from_db will find the group we created above,
    # so wait_for_workspace_event should return early without polling

    group_data = {"name": "existing_group", "host_ids": []}
    response = flask_client.post(
        "/api/inventory/v1/groups",
        data=json.dumps(group_data),
        headers={"x-rh-identity": to_auth_header(Identity(obj=USER_IDENTITY)), "Content-Type": "application/json"},
    )

    assert response.status_code == 201
    # poll() should NOT have been called since we found the group via DB check
    mock_pg_listen_connection.poll.assert_not_called()


@pytest.mark.usefixtures("enable_kessel", "event_producer")
def test_wait_for_workspace_event_succeeds_when_notify_received(
    flask_client: TestClient,
    db_create_group: Callable[..., Group],
    mocker: MockerFixture,
    mock_pg_listen_connection: MagicMock,
) -> None:
    """Test that wait_for_workspace_event succeeds when NOTIFY is received.

    This tests the normal flow: DB check doesn't find the group (it's being created),
    but we receive the NOTIFY event and succeed.
    """
    # Create a group in the database that will be returned after wait_for_workspace_event
    existing_group = db_create_group("new_group")
    workspace_id = str(existing_group.id)

    # Mock post_rbac_workspace to return the workspace ID
    mocker.patch("api.group.post_rbac_workspace", return_value=workspace_id)
    mocker.patch("lib.group_repository.rbac_create_ungrouped_hosts_workspace", return_value=generate_uuid())

    # Mock the internal DB check to return None (group not found yet)
    # This is the check inside wait_for_workspace_event
    original_get_group = __import__(
        "lib.group_repository", fromlist=["get_group_by_id_from_db"]
    ).get_group_by_id_from_db
    call_count = {"count": 0}

    def mock_get_group_for_wait(group_id: str, org_id: str, session: None = None) -> Group | None:
        call_count["count"] += 1
        # First call is the check inside wait_for_workspace_event - return None
        if call_count["count"] == 1:
            return None
        # Subsequent calls (e.g., after waiting) should return the real group
        return original_get_group(group_id, org_id, session)

    mocker.patch("lib.group_repository.get_group_by_id_from_db", side_effect=mock_get_group_for_wait)

    # Simulate receiving the NOTIFY event
    mock_notify = mocker.MagicMock()
    mock_notify.payload = workspace_id
    mock_pg_listen_connection.notifies = [mock_notify]

    group_data = {"name": "new_group", "host_ids": []}
    response = flask_client.post(
        "/api/inventory/v1/groups",
        data=json.dumps(group_data),
        headers={"x-rh-identity": to_auth_header(Identity(obj=USER_IDENTITY)), "Content-Type": "application/json"},
    )

    assert response.status_code == 201
    # poll() SHOULD have been called since DB check returned None
    mock_pg_listen_connection.poll.assert_called_once()


@pytest.mark.usefixtures("enable_kessel")
def test_wait_for_workspace_event_times_out_when_both_checks_fail(
    flask_client: TestClient,
    mocker: MockerFixture,
    mock_pg_listen_connection: MagicMock,
    inventory_config: Config,
) -> None:
    """Test that wait_for_workspace_event times out when both DB check and NOTIFY fail.

    This tests the failure scenario: DB check doesn't find the group AND no NOTIFY
    is received within the timeout period.
    """
    workspace_id = str(generate_uuid())

    # Mock post_rbac_workspace to return the workspace ID
    mocker.patch("api.group.post_rbac_workspace", return_value=workspace_id)
    mocker.patch("lib.group_repository.rbac_create_ungrouped_hosts_workspace", return_value=generate_uuid())

    # Mock the internal DB check to always return None (group never found)
    mocker.patch("lib.group_repository.get_group_by_id_from_db", return_value=None)

    # No notifications will be received (empty list)
    mock_pg_listen_connection.notifies = []

    # Use a very short timeout to speed up the test
    inventory_config.rbac_timeout = 0.1

    group_data = {"name": "timeout_group", "host_ids": []}
    response = flask_client.post(
        "/api/inventory/v1/groups",
        data=json.dumps(group_data),
        headers={"x-rh-identity": to_auth_header(Identity(obj=USER_IDENTITY)), "Content-Type": "application/json"},
    )

    # Should return 503 Service Unavailable on timeout
    assert response.status_code == 503
    # poll() SHOULD have been called (we tried to wait for notifications)
    mock_pg_listen_connection.poll.assert_called()

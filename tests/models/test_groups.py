from copy import deepcopy

import pytest
from marshmallow import ValidationError as MarshmallowValidationError

from app.exceptions import ValidationException
from app.models import InputGroupSchema
from app.queue.events import EventType
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import generate_uuid


def test_create_delete_group_happy(db_create_group, db_get_group_by_id, db_delete_group):
    group_name = "Host Group 1"

    # Verify that the group is created successfully
    created_group = db_create_group(group_name)
    assert db_get_group_by_id(created_group.id).name == group_name

    # Verify that the same group is deleted successfully
    db_delete_group(created_group.id)
    assert db_get_group_by_id(created_group.id) is None


def test_create_group_no_name(db_create_group):
    # Make sure we can't create a group with an empty name

    with pytest.raises(ValidationException):
        db_create_group(None)


def test_create_group_existing_name_diff_org(db_create_group, db_get_group_by_id):
    # Make sure we can't create two groups with the same name in the same org
    group_name = "TestGroup_diff_org"

    group1 = db_create_group(group_name)
    assert db_get_group_by_id(group1.id).name == group_name

    diff_identity = deepcopy(SYSTEM_IDENTITY)
    diff_identity["org_id"] = "diff_id"
    diff_identity["account"] = "diff_id"

    group2 = db_create_group(group_name, diff_identity)

    assert db_get_group_by_id(group2.id).name == group_name


def test_add_delete_host_group_happy(
    db_create_host,
    db_create_group,
    db_create_host_group_assoc,
    db_get_hosts_for_group,
    db_get_groups_for_host,
    db_remove_hosts_from_group,
):
    hosts_to_create = 3
    host_display_name_base = "hostgroup test host"
    group_name = "Test Group Happy"

    # Create a group to associate with the hosts
    created_group = db_create_group(group_name)
    created_host_list = []

    for index in range(hosts_to_create):
        created_host = db_create_host(
            SYSTEM_IDENTITY,
            extra_data={
                "display_name": f"{host_display_name_base}_{index}",
                "system_profile_facts": {"owner_id": SYSTEM_IDENTITY["system"]["cn"]},
            },
        )

        # Put the created host in the created group
        db_create_host_group_assoc(host_id=created_host.id, group_id=created_group.id)

        # Assert that the host that was just inserted has the correct group
        retrieved_group = db_get_groups_for_host(created_host.id)[0]
        assert retrieved_group.name == group_name
        created_host_list.append(created_host)

    # Fetch the list of hosts that we just created
    retrieved_host_list = db_get_hosts_for_group(created_group.id)

    # Verify that each host we created is present in the retrieved list
    for host in created_host_list:
        assert host in retrieved_host_list

    # Remove all hosts but one from the group
    host_ids_to_remove = [host.id for host in created_host_list][1:hosts_to_create]
    db_remove_hosts_from_group(host_ids_to_remove, created_group.id)

    # Assert that the first host is still in the group (and that the others are not)
    retrieved_host_list = db_get_hosts_for_group(created_group.id)
    assert len(retrieved_host_list) == 1
    assert created_host_list[0].id == retrieved_host_list[0].id


@pytest.mark.parametrize(
    "data",
    [
        {"name": ""},  # Name cannot be blank
        {"name": "a" * 256},  # Name must be 255 chars or less
        {"name": "test!group"},  # Special characters not allowed
        {"name": "test@group"},  # Special characters not allowed
        {"name": "name/slashes"},  # Special characters not allowed
        {"name": "name.dots"},  # Special characters not allowed
        {"host_ids": ["asdf", "foobar"]},  # Host IDs must be in UUID format
        {"foo": "bar"},  # Field does not exist
    ],
)
def test_group_schema_validation(data):
    with pytest.raises(MarshmallowValidationError):
        InputGroupSchema().load(data)


def test_serialize_group_with_host_count_false(flask_app, mocker):  # noqa: ARG001
    """serialize_group(with_host_count=False) should skip the host count query."""
    from lib.group_repository import serialize_group

    mock_group = mocker.Mock()
    mock_group.id = "test-group-id"
    mock_group.name = "Test Group"
    mock_group.org_id = "test_org"

    count_spy = mocker.patch("lib.group_repository.get_host_counts_batch")
    mocker.patch(
        "lib.group_repository.serialize_db_group_with_host_count",
        return_value={"id": "test-group-id", "name": "Test Group", "host_count": 0},
    )

    result = serialize_group(mock_group, "test_org", with_host_count=False)

    count_spy.assert_not_called()
    assert result["host_count"] == 0


def test_serialize_group_with_host_count_true(flask_app, mocker):  # noqa: ARG001
    """serialize_group(with_host_count=True) should query for host count (default behavior)."""
    from lib.group_repository import serialize_group

    mock_group = mocker.Mock()
    mock_group.id = "test-group-id"

    count_spy = mocker.patch(
        "lib.group_repository.get_host_counts_batch",
        return_value={"test-group-id": 42},
    )
    mocker.patch(
        "lib.group_repository.serialize_db_group_with_host_count",
        return_value={"id": "test-group-id", "host_count": 42},
    )

    result = serialize_group(mock_group, "test_org")

    count_spy.assert_called_once()
    assert result["host_count"] == 42


def test_ungrouped_group_cache_context_manager(flask_app, mocker):  # noqa: ARG001
    """UngroupedGroupCache should prevent duplicate Group DB queries."""
    from lib.group_repository import UngroupedGroupCache

    assert UngroupedGroupCache.get("org1") is None

    with UngroupedGroupCache():
        mock_group = mocker.Mock()
        UngroupedGroupCache.put("org1", mock_group)
        assert UngroupedGroupCache.get("org1") is mock_group

    assert UngroupedGroupCache.get("org1") is None


def test_ungrouped_group_cache_deduplicates_existing_group_lookup(flask_app, mocker):  # noqa: ARG001
    """When ungrouped group exists, a second call within the same cache context should skip DB."""
    from lib.group_repository import UngroupedGroupCache
    from lib.group_repository import get_or_create_ungrouped_hosts_group_for_identity

    mock_identity = mocker.Mock()
    mock_identity.org_id = "test_org"
    mock_identity.account_number = "test_account"

    mock_group = mocker.Mock(name="existing_ungrouped_group")
    get_ungrouped = mocker.patch("lib.group_repository.get_ungrouped_group", return_value=mock_group)
    mock_add = mocker.patch("lib.group_repository.add_group")

    with UngroupedGroupCache():
        first = get_or_create_ungrouped_hosts_group_for_identity(mock_identity)
        second = get_or_create_ungrouped_hosts_group_for_identity(mock_identity)

    assert first is mock_group
    assert second is mock_group
    get_ungrouped.assert_called_once_with(mock_identity)
    mock_add.assert_not_called()


def test_ungrouped_group_cache_deduplicates_group_creation(flask_app, mocker):  # noqa: ARG001
    """When ungrouped group must be created, a second call within the same cache context should skip DB."""
    from lib.group_repository import UngroupedGroupCache
    from lib.group_repository import get_or_create_ungrouped_hosts_group_for_identity

    mock_identity = mocker.Mock()
    mock_identity.org_id = "test_org"
    mock_identity.account_number = "test_account"

    workspace_id = generate_uuid()
    mock_created_group = mocker.Mock(name="created_ungrouped_group")
    mock_config = mocker.patch("lib.group_repository.inventory_config")
    mock_config.return_value.bypass_kessel = False
    get_ungrouped = mocker.patch("lib.group_repository.get_ungrouped_group", return_value=None)
    mock_rbac = mocker.patch("lib.group_repository.rbac_create_ungrouped_hosts_workspace", return_value=workspace_id)
    mock_wait = mocker.patch("lib.group_repository.wait_for_workspace_event")
    mocker.patch("lib.group_repository.is_rbac_v2_enabled", return_value=False)
    mock_get_by_id = mocker.patch("lib.group_repository.get_group_by_id_from_db", return_value=mock_created_group)

    with UngroupedGroupCache():
        first = get_or_create_ungrouped_hosts_group_for_identity(mock_identity)
        second = get_or_create_ungrouped_hosts_group_for_identity(mock_identity)

    assert first is mock_created_group
    assert second is mock_created_group
    get_ungrouped.assert_called_once_with(mock_identity)
    mock_rbac.assert_called_once_with(mock_identity)
    mock_wait.assert_called_once_with(
        str(workspace_id),
        EventType.created,
        org_id=mock_identity.org_id,
        timeout=mock_config.return_value.rbac_timeout,
    )
    mock_get_by_id.assert_called_once_with(str(workspace_id), "test_org")


def test_ungrouped_group_cache_deduplicates_group_creation_rbac_v2(flask_app, mocker):  # noqa: ARG001
    """When RBAC v2 is enabled, the ungrouped group is still loaded from the DB after the workspace event.

    Callers (including MQ ingest) need a Group ORM object with .id. Fetching the workspace from the
    RBAC HTTP API would require a Flask request context that MQ does not have.
    """
    from lib.group_repository import UngroupedGroupCache
    from lib.group_repository import get_or_create_ungrouped_hosts_group_for_identity

    mock_identity = mocker.Mock()
    mock_identity.org_id = "test_org"
    mock_identity.account_number = "test_account"

    workspace_id = generate_uuid()
    mock_created_group = mocker.Mock(name="created_ungrouped_group")
    mock_config = mocker.patch("lib.group_repository.inventory_config")
    mock_config.return_value.bypass_kessel = False
    get_ungrouped = mocker.patch("lib.group_repository.get_ungrouped_group", return_value=None)
    mock_rbac = mocker.patch("lib.group_repository.rbac_create_ungrouped_hosts_workspace", return_value=workspace_id)
    mock_wait = mocker.patch("lib.group_repository.wait_for_workspace_event")
    mocker.patch("lib.group_repository.is_rbac_v2_enabled", return_value=True)
    mock_get_by_id = mocker.patch("lib.group_repository.get_group_by_id_from_db", return_value=mock_created_group)
    mock_get_rbac_ws = mocker.patch("lib.middleware.get_rbac_workspace_by_id")

    with UngroupedGroupCache():
        first = get_or_create_ungrouped_hosts_group_for_identity(mock_identity)
        second = get_or_create_ungrouped_hosts_group_for_identity(mock_identity)

    assert first is mock_created_group
    assert second is mock_created_group
    get_ungrouped.assert_called_once_with(mock_identity)
    mock_rbac.assert_called_once_with(mock_identity)
    mock_wait.assert_called_once()
    mock_get_by_id.assert_called_once_with(str(workspace_id), "test_org")
    mock_get_rbac_ws.assert_not_called()


@pytest.mark.parametrize(
    "failing_function,side_effect,expected_exception",
    [
        ("rbac_create_ungrouped_hosts_workspace", RuntimeError("RBAC creation failed"), RuntimeError),
        ("wait_for_workspace_event", TimeoutError("Timed out"), TimeoutError),
    ],
)
def test_ungrouped_group_creation_failure_increments_metric(
    flask_app,  # noqa: ARG001
    mocker,
    failing_function,
    side_effect,
    expected_exception,
):
    """When the kessel-enabled path raises an exception, the failure metric is incremented."""
    from lib.group_repository import UngroupedGroupCache
    from lib.group_repository import get_or_create_ungrouped_hosts_group_for_identity

    mock_identity = mocker.Mock()
    mock_identity.org_id = "test_org"

    mock_config = mocker.patch("lib.group_repository.inventory_config")
    mock_config.return_value.bypass_kessel = False
    mock_config.return_value.rbac_timeout = 10
    mocker.patch("lib.group_repository.get_ungrouped_group", return_value=None)
    mocker.patch("lib.group_repository.rbac_create_ungrouped_hosts_workspace", return_value=generate_uuid())
    mocker.patch("lib.group_repository.wait_for_workspace_event")
    mocker.patch(f"lib.group_repository.{failing_function}", side_effect=side_effect)
    mock_metric = mocker.patch("lib.group_repository.ungrouped_hosts_group_creation_failure")

    with UngroupedGroupCache(), pytest.raises(expected_exception):
        get_or_create_ungrouped_hosts_group_for_identity(mock_identity)

    mock_metric.inc.assert_called_once()


@pytest.mark.parametrize("bypass_kessel", [True, False])
def test_ungrouped_group_creation_success_does_not_increment_metric(flask_app, mocker, bypass_kessel):  # noqa: ARG001
    """When ungrouped hosts group creation succeeds, the failure metric is not incremented."""
    from lib.group_repository import UngroupedGroupCache
    from lib.group_repository import get_or_create_ungrouped_hosts_group_for_identity

    mock_identity = mocker.Mock()
    mock_identity.org_id = "test_org"
    mock_identity.account_number = "test_account"

    mock_created_group = mocker.Mock(name="created_ungrouped_group")
    mock_config = mocker.patch("lib.group_repository.inventory_config")
    mock_config.return_value.bypass_kessel = bypass_kessel
    mock_config.return_value.rbac_timeout = 10
    mocker.patch("lib.group_repository.get_ungrouped_group", return_value=None)
    mocker.patch("lib.group_repository.add_group", return_value=mock_created_group)
    mocker.patch("lib.group_repository.rbac_create_ungrouped_hosts_workspace", return_value=generate_uuid())
    mocker.patch("lib.group_repository.wait_for_workspace_event")
    mocker.patch("lib.group_repository.get_group_by_id_from_db", return_value=mock_created_group)
    mock_metric = mocker.patch("lib.group_repository.ungrouped_hosts_group_creation_failure")

    with UngroupedGroupCache():
        group = get_or_create_ungrouped_hosts_group_for_identity(mock_identity)

    assert group is mock_created_group
    mock_metric.inc.assert_not_called()

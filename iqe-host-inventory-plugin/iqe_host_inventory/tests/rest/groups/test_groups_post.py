from __future__ import annotations

import logging
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from uuid import UUID

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.tests.rest.validation.test_system_profile import INCORRECT_STRING_VALUES
from iqe_host_inventory.utils import assert_datetimes_equal
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import generate_digits
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_sp_field_value
from iqe_host_inventory.utils.datagen_utils import generate_string_of_length
from iqe_host_inventory.utils.datagen_utils import generate_timestamp
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.datagen_utils import get_sp_field_by_name
from iqe_host_inventory_api import ApiValueError
from iqe_host_inventory_api.models import GroupOutWithHostCount

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)


@pytest.mark.parametrize(
    "hosts_list",
    [None, [], "single_host", "multiple_hosts"],
    ids=["not present", "empty list", "single host", "multiple hosts"],
)
@pytest.mark.ephemeral
def test_groups_create_response(
    host_inventory: ApplicationHostInventory,
    hbi_default_org_id: str,
    hbi_default_account_number: str,
    hosts_list: str | list | None,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3828
    https://issues.redhat.com/browse/RHINENG-21925

    metadata:
      requirements: inv-groups-post
      assignee: fstavela
      importance: medium
      title: Test response for POST /groups request
    """
    hosts = host_inventory.kafka.create_random_hosts(3)
    if hosts_list == "single_host":
        assigned_hosts = [hosts[0].id]
    elif hosts_list == "multiple_hosts":
        assigned_hosts = [host.id for host in hosts]
    else:
        assigned_hosts = hosts_list  # type: ignore[assignment]

    group_name = generate_display_name()
    data: dict[str, list[str] | str] = {"name": group_name}
    if assigned_hosts is not None:
        data["host_ids"] = assigned_hosts
    time1 = datetime.now(tz=UTC)
    response = host_inventory.apis.groups.raw_api.api_group_create_group_with_http_info(data)
    time2 = datetime.now(tz=UTC)

    assert response[1] == 201
    group: GroupOutWithHostCount = response[0]

    assert UUID(group.id)
    assert group.name == group_name
    assert group.org_id == hbi_default_org_id
    assert group.account == hbi_default_account_number
    assert group.ungrouped is False
    assert time1 < group.created < time2
    # With kessel sync, even an empty list will take longer
    # time_delta = 100 if hosts_list else 1
    time_delta = 100
    assert_datetimes_equal(group.updated, group.created, timedelta(milliseconds=time_delta))

    if not assigned_hosts:
        assert group.host_count == 0
    else:
        assert group.host_count == len(assigned_hosts)


@pytest.mark.parametrize("hosts_list", [[], None], ids=["empty list", "not present"])
def test_groups_create_empty(host_inventory, hosts_list):
    """
    https://issues.redhat.com/browse/ESSNTL-3828

    metadata:
      requirements: inv-groups-post
      assignee: fstavela
      importance: high
      title: Create a group without any hosts
    """
    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(
        group_name, hosts=hosts_list, wait_for_created=False
    )
    assert group.id
    assert group.name == group_name
    assert group.host_count == 0
    host_inventory.apis.groups.verify_updated(group, name=group_name, hosts=[])


@pytest.mark.ephemeral
@pytest.mark.parametrize("host_type", ["conventional", "edge", "image-mode"])
def test_groups_create_with_one_host(host_inventory: ApplicationHostInventory, host_type: str):
    """
    https://issues.redhat.com/browse/ESSNTL-3828
    https://issues.redhat.com/browse/RHINENG-8990

    metadata:
      requirements: inv-groups-post
      assignee: fstavela
      importance: high
      title: Create a group with one host
    """
    sp_bootc = get_sp_field_by_name("bootc_status")
    hosts_data = host_inventory.datagen.create_n_hosts_data(3)

    if host_type == "edge":
        for host_data in hosts_data:
            host_data["system_profile"]["host_type"] = "edge"
    if host_type == "image-mode":
        for host_data in hosts_data:
            host_data["system_profile"]["bootc_status"] = generate_sp_field_value(sp_bootc)

    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(
        group_name, hosts=hosts[0], wait_for_created=False
    )
    assert group.id
    assert group.name == group_name
    assert group.host_count == 1
    host_inventory.apis.groups.verify_updated(group, name=group_name, hosts=hosts[0])


@pytest.mark.ephemeral
@pytest.mark.parametrize("host_type", ["conventional", "edge", "image-mode", "all"])
def test_groups_create_with_multiple_hosts(
    host_inventory: ApplicationHostInventory, host_type: str
):
    """
    https://issues.redhat.com/browse/ESSNTL-3828
    https://issues.redhat.com/browse/RHINENG-8990

    metadata:
      requirements: inv-groups-post
      assignee: fstavela
      importance: high
      title: Create a group with multiple hosts
    """
    sp_bootc = get_sp_field_by_name("bootc_status")
    hosts_data = host_inventory.datagen.create_n_hosts_data(3)

    if host_type == "edge":
        for host_data in hosts_data:
            host_data["system_profile"]["host_type"] = "edge"
    if host_type == "image-mode":
        for host_data in hosts_data:
            host_data["system_profile"]["bootc_status"] = generate_sp_field_value(sp_bootc)
    if host_type == "all":
        hosts_data[1]["system_profile"]["host_type"] = "edge"
        hosts_data[2]["system_profile"]["bootc_status"] = generate_sp_field_value(sp_bootc)

    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(
        group_name, hosts=hosts, wait_for_created=False
    )
    assert group.id
    assert group.name == group_name
    assert group.host_count == 3
    host_inventory.apis.groups.verify_updated(group, name=group_name, hosts=hosts)


@pytest.mark.ephemeral
@pytest.mark.parametrize("which_hosts", ["only_same", "new_and_same"])
def test_groups_create_two_groups_same_host(
    host_inventory: ApplicationHostInventory, which_hosts: str
):
    """
    https://issues.redhat.com/browse/ESSNTL-3828

    metadata:
      requirements: inv-groups-post
      assignee: fstavela
      importance: medium
      negative: true
      title: Try to create two groups with the same host
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    group_name1 = generate_display_name()
    group1 = host_inventory.apis.groups.create_group(group_name1, hosts=hosts[0])
    group_name2 = generate_display_name()
    group2_hosts = [hosts[0]] if which_hosts == "only_same" else hosts
    with raises_apierror(
        400,
        "The following subset of hosts are already associated with another group: "
        f"['{hosts[0].id}'].",
    ):
        host_inventory.apis.groups.create_group(
            group_name2, hosts=group2_hosts, wait_for_created=False
        )

    host_inventory.apis.groups.verify_not_created(group_name2)
    host_inventory.apis.groups.verify_not_updated(group1, name=group_name1, hosts=hosts[0])

    response = host_inventory.apis.hosts.get_hosts(group_name=[group_name2])
    assert response == []
    response = host_inventory.apis.hosts.get_hosts(group_name=[group_name1])
    assert len(response) == 1
    assert response[0].id == hosts[0].id


@pytest.mark.ephemeral
def test_groups_create_different_account_name(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3828

    metadata:
      requirements: inv-groups-post
      assignee: fstavela
      importance: high
      title: Create a group with the same name as group in different account
    """
    hosts = host_inventory_secondary.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    group_secondary = host_inventory_secondary.apis.groups.create_group(group_name, hosts=hosts)
    group_primary = host_inventory.apis.groups.create_group(group_name, wait_for_created=False)

    assert group_primary.id != group_secondary.id
    host_inventory_secondary.apis.groups.verify_not_updated(
        group_secondary, name=group_name, hosts=hosts
    )
    host_inventory.apis.groups.verify_updated(group_primary, name=group_name, hosts=[])


@pytest.mark.ephemeral
def test_groups_create_different_account_hosts(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3828

    metadata:
      requirements: inv-groups-post
      assignee: fstavela
      importance: critical
      title: Try to create a group with hosts from different account
    """
    host = host_inventory_secondary.kafka.create_host()

    group_name = generate_display_name()
    with raises_apierror(400, f"Could not find existing host(s) with ID {{'{host.id}'}}."):
        host_inventory.apis.groups.create_group(group_name, hosts=host, wait_for_created=False)

    host_inventory.apis.groups.verify_not_created(group_name)
    response = host_inventory.apis.hosts.get_hosts(group_name=[group_name])
    assert len(response) == 0


def test_groups_create_without_data(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-3828

    metadata:
      requirements: inv-groups-post
      assignee: fstavela
      importance: low
      negative: true
      title: Try to create a group without sending any data
    """
    with host_inventory.apis.groups.verify_group_count_not_changed():
        with pytest.raises(ApiValueError) as exc:
            host_inventory.apis.groups.raw_api.api_group_create_group(None)
        assert exc.value.args == (
            "Missing the required parameter `group_in` when calling `api_group_create_group`",
        )


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "host_ids",
    ["not-present", "empty-list", "with-id"],
    ids=["not present", "empty list", "with ID"],
)
def test_groups_create_without_name(host_inventory: ApplicationHostInventory, host_ids: str):
    """
    https://issues.redhat.com/browse/ESSNTL-3828

    metadata:
      requirements: inv-groups-post
      assignee: fstavela
      importance: low
      negative: true
      title: Try to create a group without providing a name
    """
    host = host_inventory.kafka.create_host()
    data = {}
    if host_ids != "not-present":
        data["host_ids"] = [] if host_ids == "empty-list" else [host.id]

    with host_inventory.apis.groups.verify_group_count_not_changed():
        with raises_apierror(400):
            host_inventory.apis.groups.raw_api.api_group_create_group(data)


@pytest.mark.parametrize(
    "group_name",
    [generate_string_of_length(0), generate_string_of_length(256)],
    ids=["too short", "too long"],
)
def test_groups_create_validate_name_wrong_length(host_inventory, group_name):
    """
    https://issues.redhat.com/browse/ESSNTL-3828

    metadata:
      requirements: inv-groups-post
      assignee: fstavela
      importance: low
      negative: true
      title: Try to create a group with the name of a wrong length
    """
    with raises_apierror(400, "'name': ['Length must be between 1 and 255.']"):
        host_inventory.apis.groups.create_group(group_name, wait_for_created=False)

    if group_name != "":
        host_inventory.apis.groups.verify_not_created(group_name)


@pytest.mark.parametrize(
    "group_name",
    (
        *INCORRECT_STRING_VALUES,
        pytest.param(None, id="None"),
    ),
)
def test_groups_create_validate_name_wrong_type(host_inventory, group_name):
    """
    https://issues.redhat.com/browse/ESSNTL-3828

    metadata:
      requirements: inv-groups-post
      assignee: fstavela
      importance: low
      negative: true
      title: Try to create a group with a non-string name
    """
    with raises_apierror(400, f"{group_name} is not of type 'string' - 'name'"):
        host_inventory.apis.groups.create_group(group_name, wait_for_created=False)

    if (
        not isinstance(group_name, dict)
        and not isinstance(group_name, list)
        and group_name is not None
    ):
        host_inventory.apis.groups.verify_not_created(group_name)


@pytest.mark.parametrize(
    "host_ids, error_type",
    [
        (generate_uuid(), "list"),
        ([generate_uuid()[:35]], "match"),
        ([generate_uuid() + "a"], "match"),
        ([generate_uuid().replace("-", "_")], "match"),
        ([generate_uuid().replace("-", "")], "uuid"),
        ([generate_string_of_length(36)], "match"),
    ],
    ids=["not a list", "too short", "too long", "underscores", "without dashes", "random string"],
)
def test_groups_create_validate_host_ids_wrong(
    host_inventory: ApplicationHostInventory, host_ids, error_type
):
    """
    https://issues.redhat.com/browse/ESSNTL-3828

    metadata:
      requirements: inv-groups-post
      assignee: fstavela
      importance: low
      negative: true
      title: Try to create a group with host IDs of a wrong format
    """
    err_msgs: tuple[str, ...]
    if error_type == "list":
        err_msgs = (f"'{host_ids}' is not of type 'array' - 'host_ids'",)
    elif error_type == "uuid":
        err_msgs = (f"'{host_ids[0]}' is not a 'uuid' - 'host_ids.0'",)
    else:
        host_ids[0] = host_ids[0].replace("'", "").replace('"', "").replace("\\", "")
        err_msgs = (f"'{host_ids[0]}' does not match", " - 'host_ids.0'")

    group_name = generate_display_name()
    data = {"name": group_name, "host_ids": host_ids}
    with raises_apierror(400, err_msgs):
        host_inventory.apis.groups.raw_api.api_group_create_group(data)

    host_inventory.apis.groups.verify_not_created(group_name)
    response = host_inventory.apis.hosts.get_hosts(group_name=[group_name])
    assert len(response) == 0


def test_groups_create_with_not_existing_host(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-3828

    metadata:
      requirements: inv-groups-post
      assignee: fstavela
      importance: medium
      title: Create a group with correct and bad host IDs
    """
    host_ids = [generate_uuid()]

    group_name = generate_display_name()
    with raises_apierror(400, f"Could not find existing host(s) with ID {set(host_ids)}"):
        host_inventory.apis.groups.create_group(group_name, hosts=host_ids, wait_for_created=False)

    host_inventory.apis.groups.verify_not_created(group_name)
    response = host_inventory.apis.hosts.get_hosts(group_name=[group_name])
    assert len(response) == 0


@pytest.mark.ephemeral
def test_groups_create_with_good_and_not_existing_hosts(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-3828

    metadata:
      requirements: inv-groups-post
      assignee: fstavela
      importance: medium
      title: Create a group with correct and bad host IDs
    """
    hosts = host_inventory.kafka.create_random_hosts(3)
    host_ids = [hosts[0].id, generate_uuid(), hosts[1].id]

    group_name = generate_display_name()
    with raises_apierror(400, f"Could not find existing host(s) with ID {{'{host_ids[1]}'}}."):
        host_inventory.apis.groups.create_group(group_name, hosts=host_ids, wait_for_created=False)

    host_inventory.apis.groups.verify_not_created(group_name)
    response = host_inventory.apis.hosts.get_hosts(group_name=[group_name])
    assert len(response) == 0


@pytest.mark.ephemeral
def test_groups_create_with_good_and_bad_hosts(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-3828

    metadata:
      requirements: inv-groups-post
      assignee: fstavela
      importance: medium
      title: Create a group with correct and bad host IDs
    """
    bad_id = generate_string_of_length(10).replace("'", "").replace('"', "").replace("\\", "")
    hosts = host_inventory.kafka.create_random_hosts(3)
    host_ids = [hosts[0].id, bad_id, hosts[1].id]

    group_name = generate_display_name()
    with raises_apierror(400, (f"'{host_ids[1]}' does not match", " - 'host_ids.1'")):
        host_inventory.apis.groups.create_group(group_name, hosts=host_ids)

    host_inventory.apis.groups.verify_not_created(group_name)
    response = host_inventory.apis.hosts.get_hosts(group_name=[group_name])
    assert len(response) == 0


@pytest.mark.parametrize(
    "field, value",
    [
        ("id", generate_uuid()),
        ("account", generate_digits(5)),
        ("created_on", generate_timestamp()),
        ("modified_on", generate_timestamp()),
    ],
    ids=["id", "account", "created_on", "updated_on"],
)
def test_groups_create_validate_protected_fields(
    host_inventory: ApplicationHostInventory, field, value
):
    """
    https://issues.redhat.com/browse/ESSNTL-3828

    metadata:
      requirements: inv-groups-post
      assignee: fstavela
      importance: medium
      negative: true
      title: Try to create a group with changing protected fields
    """
    group_name = generate_display_name()
    data = {"name": group_name, "host_ids": [], field: value}
    with raises_apierror(400, f"{{'{field}': ['Unknown field.']}}"):
        host_inventory.apis.groups.raw_api.api_group_create_group(data)

    host_inventory.apis.groups.verify_not_created(group_name)


@pytest.mark.parametrize("org_id", ["same", "different"])
def test_groups_create_with_changed_org_id(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
    org_id,
    hbi_default_org_id,
    hbi_secondary_org_id,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3828

    metadata:
      requirements: inv-groups-post
      assignee: fstavela
      importance: high
      negative: true
      title: Try to create a group with changing the org_id
    """
    value = hbi_default_org_id if org_id == "same" else hbi_secondary_org_id
    group_name = generate_display_name()
    data = {"name": group_name, "host_ids": [], "org_id": value}
    with raises_apierror(400, "{'org_id': ['Unknown field.']}"):
        host_inventory.apis.groups.raw_api.api_group_create_group(data)

    host_inventory.apis.groups.verify_not_created(group_name)
    host_inventory_secondary.apis.groups.verify_not_created(group_name)


def test_groups_create_with_random_field(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-3828

    metadata:
      requirements: inv-groups-post
      assignee: fstavela
      importance: low
      negative: true
      title: Try to create a group with adding new field
    """
    group_name = generate_display_name()
    data = {"name": group_name, "host_ids": [], "field123": "value123"}
    with raises_apierror(400, "{'field123': ['Unknown field.']}"):
        host_inventory.apis.groups.raw_api.api_group_create_group(data)

    host_inventory.apis.groups.verify_not_created(group_name)


def test_groups_create_strip_whitespace(host_inventory):
    """
    https://issues.redhat.com/browse/RHINENG-3108

    metadata:
      requirements: inv-groups-post
      assignee: fstavela
      importance: medium
      negative: true
      title: Test that Inventory strips a group name from whitespaces when creating a new group
    """
    group_name = " " + generate_display_name() + " "
    stripped_name = group_name.strip()

    group = host_inventory.apis.groups.create_group(group_name)
    assert group.name == stripped_name

    response_group = host_inventory.apis.groups.get_group_by_id(group)
    assert response_group.name == stripped_name

    response_groups = host_inventory.apis.groups.get_groups(name=stripped_name)
    assert len(response_groups) == 1
    assert response_groups[0] == group


@pytest.mark.ephemeral
def test_groups_create_with_the_same_host_multiple_times(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-10846
    https://issues.redhat.com/browse/RHINENG-10845

    metadata:
      requirements: inv-groups-post
      assignee: fstavela
      importance: low
      negative: true
      title: Try to create a group with the same Host ID multiple times in the data
    """
    host = host_inventory.kafka.create_host()
    group_name = generate_display_name()
    with raises_apierror(400, "Host IDs must be unique."):
        host_inventory.apis.groups.create_group(
            group_name, hosts=[host.id, host.id], wait_for_created=False
        )

    host_inventory.apis.groups.verify_not_created(group_name)

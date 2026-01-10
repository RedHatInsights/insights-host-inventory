from __future__ import annotations

import logging
from datetime import UTC
from datetime import datetime
from time import sleep
from typing import Any
from uuid import UUID

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.tests.rest.validation.test_system_profile import INCORRECT_CANONICAL_UUIDS
from iqe_host_inventory.tests.rest.validation.test_system_profile import INCORRECT_STRING_VALUES
from iqe_host_inventory.utils.api_utils import api_disabled_validation
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import generate_digits
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_string_of_length
from iqe_host_inventory.utils.datagen_utils import generate_timestamp
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory_api.models import GroupOutWithHostCount

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "fields", [("host_ids",), ("name",), ("host_ids", "name")], ids=["host_ids", "name", "both"]
)
def test_groups_patch_response(
    host_inventory: ApplicationHostInventory,
    hbi_default_org_id: str,
    hbi_default_account_number: str,
    fields: tuple[str, ...],
):
    """
    https://issues.redhat.com/browse/ESSNTL-3851
    https://issues.redhat.com/browse/RHINENG-21925

    metadata:
      requirements: inv-groups-patch
      assignee: fstavela
      importance: medium
      title: Test response for PATCH /groups/<group_id> request
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    time1 = datetime.now(tz=UTC)
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts[0])
    time2 = datetime.now(tz=UTC)

    expected_name = generate_display_name() if "name" in fields else group_name
    expected_host_ids = [host.id for host in hosts] if "host_ids" in fields else [hosts[0].id]
    data: dict[str, str | list[str]] = {}
    if "host_ids" in fields:
        data["host_ids"] = expected_host_ids
    if "name" in fields:
        data["name"] = expected_name
    response = host_inventory.apis.groups.raw_api.api_group_patch_group_by_id_with_http_info(
        group.id, data
    )
    time3 = datetime.now(tz=UTC)

    assert response[1] == 200
    updated_group: GroupOutWithHostCount = response[0]

    assert updated_group.id == group.id
    assert updated_group.name == expected_name
    assert updated_group.host_count == len(expected_host_ids)
    assert updated_group.org_id == hbi_default_org_id
    assert updated_group.account == hbi_default_account_number
    assert updated_group.ungrouped is False
    assert time1 < updated_group.created < time2
    assert time2 < updated_group.updated < time3


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "fields",
    [["name"], ["hosts"], ["name", "hosts"]],
    ids=["only name", "only hosts", "name and hosts"],
)
@pytest.mark.parametrize("with_hosts", [False, True], ids=["empty group", "group with hosts"])
def test_groups_patch_not_update(
    host_inventory: ApplicationHostInventory,
    fields: list[str],
    with_hosts: bool,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3851

    metadata:
      requirements: inv-groups-patch
      assignee: fstavela
      importance: high
      title: Update a group with the same data
    """
    hosts = host_inventory.kafka.create_random_hosts(3) if with_hosts else []
    hosts_ids = {host.id for host in hosts}

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)

    params: dict[str, str | list[HostWrapper]] = {}
    if "name" in fields:
        params["name"] = group_name
    if "hosts" in fields:
        params["hosts"] = hosts

    response = host_inventory.apis.groups.patch_group(group, **params, wait_for_updated=False)
    assert response.id == group.id
    assert response.name == group_name
    assert response.host_count == len(hosts_ids)

    host_inventory.apis.groups.verify_not_updated(group, name=group_name, hosts=hosts)


@pytest.mark.ephemeral
@pytest.mark.parametrize("send_hosts", [False, True], ids=["send host IDs", "don't send host IDs"])
@pytest.mark.parametrize("with_hosts", [False, True], ids=["empty group", "group with hosts"])
def test_groups_patch_name(
    host_inventory: ApplicationHostInventory,
    send_hosts: bool,
    with_hosts: bool,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3851

    metadata:
      requirements: inv-groups-patch
      assignee: fstavela
      importance: high
      title: Update a group's name
    """
    hosts = host_inventory.kafka.create_random_hosts(3) if with_hosts else []
    hosts_ids = {host.id for host in hosts}

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)

    new_name = generate_display_name()
    params: dict[str, str | list[HostWrapper]] = {"name": new_name}
    if send_hosts:
        params["hosts"] = hosts

    response = host_inventory.apis.groups.patch_group(group, **params, wait_for_updated=False)
    assert response.id == group.id
    assert response.name == new_name
    assert response.host_count == len(hosts_ids)

    host_inventory.apis.groups.verify_updated(group, name=new_name, hosts=hosts_ids)


@pytest.mark.ephemeral
@pytest.mark.parametrize("how_many", [1, 3], ids=["add a single host", "add multiple hosts"])
@pytest.mark.parametrize("send_name", [False, True], ids=["don't send name", "send name"])
@pytest.mark.parametrize("with_hosts", [False, True], ids=["empty group", "group with hosts"])
def test_groups_patch_add_hosts(
    host_inventory: ApplicationHostInventory,
    how_many: int,
    send_name: bool,
    with_hosts: bool,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3851

    metadata:
      requirements: inv-groups-patch
      assignee: fstavela
      importance: high
      title: Add hosts to group via PATCH request
    """
    hosts = host_inventory.kafka.create_random_hosts(3) if with_hosts else []

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)

    hosts += host_inventory.kafka.create_random_hosts(how_many)
    hosts_ids = {host.id for host in hosts}
    params: dict[str, str | list[HostWrapper]] = {"hosts": hosts}
    if send_name:
        params["name"] = group_name

    response = host_inventory.apis.groups.patch_group(group, **params, wait_for_updated=False)
    assert response.id == group.id
    assert response.name == group_name
    assert response.host_count == len(hosts_ids)

    host_inventory.apis.groups.verify_updated(group, name=group_name, hosts=hosts_ids)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "how_many",
    [1, 2, "all"],
    ids=["remove a single host", "remove multiple hosts", "remove all hosts"],
)
@pytest.mark.parametrize("send_name", [False, True], ids=["don't send name", "send name"])
def test_groups_patch_remove_hosts(
    host_inventory: ApplicationHostInventory,
    how_many: int | str,
    send_name: bool,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3851

    metadata:
      requirements: inv-groups-patch
      assignee: fstavela
      importance: high
      title: Remove hosts from group via PATCH request
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)

    hosts = [] if isinstance(how_many, str) else hosts[:-how_many]
    hosts_ids = {host.id for host in hosts}
    params: dict[str, str | list[HostWrapper]] = {"hosts": hosts}
    if send_name:
        params["name"] = group_name

    response = host_inventory.apis.groups.patch_group(group, **params, wait_for_updated=False)
    assert response.id == group.id
    assert response.name == group_name
    assert response.host_count == len(hosts_ids)

    host_inventory.apis.groups.verify_updated(group, name=group_name, hosts=hosts_ids)


@pytest.mark.ephemeral
def test_groups_patch_add_and_remove_hosts(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-3851

    metadata:
      requirements: inv-groups-patch
      assignee: fstavela
      importance: high
      title: Remove and add a different host to group at the same time via PATCH request
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)

    hosts.pop()
    hosts.append(host_inventory.kafka.create_host())
    hosts_ids = {host.id for host in hosts}

    response = host_inventory.apis.groups.patch_group(group, hosts=hosts, wait_for_updated=False)
    assert response.id == group.id
    assert response.name == group_name
    assert response.host_count == len(hosts_ids)

    host_inventory.apis.groups.verify_updated(group, name=group_name, hosts=hosts_ids)


@pytest.mark.ephemeral
def test_groups_patch_change_hosts(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-3851

    metadata:
      requirements: inv-groups-patch
      assignee: fstavela
      importance: high
      title: Replace group's hosts
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)

    hosts = host_inventory.kafka.create_random_hosts(3)
    hosts_ids = {host.id for host in hosts}

    response = host_inventory.apis.groups.patch_group(group, hosts=hosts, wait_for_updated=False)
    assert response.id == group.id
    assert response.name == group_name
    assert response.host_count == len(hosts_ids)

    host_inventory.apis.groups.verify_updated(group, name=group_name, hosts=hosts_ids)


def test_groups_patch_name_and_hosts(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-3851

    metadata:
      requirements: inv-groups-patch
      assignee: fstavela
      importance: high
      title: Update group's name and hosts at the same time
    """
    hosts = host_inventory.upload.create_hosts(4)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts[:2])

    new_name = generate_display_name()

    response = host_inventory.apis.groups.patch_group(
        group, name=new_name, hosts=hosts[2:], wait_for_updated=False
    )
    assert response.id == group.id
    assert response.name == new_name
    assert response.host_count == 2

    host_inventory.apis.groups.verify_updated(group, name=new_name, hosts=hosts[2:])


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "fields", [("hosts",), ("name",), ("hosts", "name")], ids=["hosts", "name", "both"]
)
def test_groups_patch_check_timestamps(
    host_inventory: ApplicationHostInventory, fields: tuple[str, ...]
):
    """
    https://issues.redhat.com/browse/ESSNTL-3851

    metadata:
      requirements: inv-groups-patch
      assignee: fstavela
      importance: medium
      title: Test that `updated` timestamp gets updated after PATCH /groups/<group_id> request
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    time1 = datetime.now(tz=UTC)
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts[0])
    time2 = datetime.now(tz=UTC)

    expected_name = generate_display_name() if "name" in fields else group_name
    expected_host_ids = [host.id for host in hosts] if "hosts" in fields else [hosts[0].id]
    data: dict[str, str | list[str]] = {}
    if "hosts" in fields:
        data["hosts"] = expected_host_ids
    if "name" in fields:
        data["name"] = expected_name
    host_inventory.apis.groups.patch_group(group, **data)
    time3 = datetime.now(tz=UTC)

    updated_group = host_inventory.apis.groups.get_group_by_id(group)

    assert updated_group.id == group.id
    assert time1 < updated_group.created < time2
    assert time2 < updated_group.updated < time3


@pytest.mark.ephemeral
def test_groups_patch_not_existing_hosts(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-3851
    https://issues.redhat.com/browse/RHINENG-21930
    https://issues.redhat.com/browse/RHINENG-18151

    metadata:
      requirements: inv-groups-patch
      assignee: fstavela
      importance: medium
      negative: true
      title: Try to update group with a not existing host
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)

    host_id = generate_uuid()
    with raises_apierror(400, f"Could not find existing host(s) with ID {{'{host_id}'}}."):
        host_inventory.apis.groups.patch_group(group, hosts=host_id, wait_for_updated=False)

    # Adding this sleep based on debugging the test in iqe pod.  If it works,
    # it may be related to kessel integration
    sleep(20)
    host_inventory.apis.groups.verify_not_updated(group, name=group_name, hosts=hosts)


@pytest.mark.ephemeral
def test_groups_patch_good_and_not_existing_hosts(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-3851
    https://issues.redhat.com/browse/RHINENG-21930
    https://issues.redhat.com/browse/RHINENG-18151

    metadata:
      requirements: inv-groups-patch
      assignee: fstavela
      importance: medium
      title: Try to update group with one existing and one not existing host at the same time
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)

    new_hosts = host_inventory.kafka.create_random_hosts(2)
    assigned_hosts = [new_hosts[0].id, generate_uuid(), new_hosts[1].id]

    with raises_apierror(
        400, f"Could not find existing host(s) with ID {{'{assigned_hosts[1]}'}}."
    ):
        host_inventory.apis.groups.patch_group(group, hosts=assigned_hosts, wait_for_updated=False)

    # Adding this sleep based on debugging the test in iqe pod.  If it works,
    # it may be related to kessel integration
    sleep(20)
    host_inventory.apis.groups.verify_not_updated(group, name=group_name, hosts=hosts)


@pytest.mark.ephemeral
def test_groups_patch_good_and_bad_hosts(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-3851

    metadata:
      requirements: inv-groups-patch, inv-api-validation
      assignee: fstavela
      importance: medium
      title: Try to update group with one good and one wrong host ID at the same time
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)

    new_hosts = host_inventory.kafka.create_random_hosts(2)
    bad_id = generate_string_of_length(10).replace("'", "").replace('"', "").replace("\\", "")
    assigned_hosts = [new_hosts[0].id, bad_id, new_hosts[1].id]

    with raises_apierror(400, (f"'{bad_id}' does not match ", " - 'host_ids.1'")):
        host_inventory.apis.groups.patch_group(group, hosts=assigned_hosts, wait_for_updated=False)

    host_inventory.apis.groups.verify_not_updated(group, name=group_name, hosts=hosts)


@pytest.mark.ephemeral
def test_groups_patch_two_groups_same_hosts(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-3851

    metadata:
      requirements: inv-groups-patch
      assignee: fstavela
      importance: high
      title: Update group's hosts to match hosts of other group
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts[:2])
    group_name2 = generate_display_name()
    group2 = host_inventory.apis.groups.create_group(group_name2, hosts=hosts[2:])

    duplicate_host_ids = [host.id for host in hosts[:2]]
    with raises_apierror(
        400,
        (
            "The following subset of hosts are already associated with another group: ",
            *duplicate_host_ids,
        ),
    ):
        host_inventory.apis.groups.patch_group(group2, hosts=hosts, wait_for_updated=False)

    host_inventory.apis.groups.verify_not_updated(group, name=group_name, hosts=hosts[:2])
    host_inventory.apis.groups.verify_not_updated(group2, name=group_name2, hosts=hosts[2:])


@pytest.mark.ephemeral
def test_groups_patch_different_account_name(
    host_inventory: ApplicationHostInventory, host_inventory_secondary: ApplicationHostInventory
):
    """
    https://issues.redhat.com/browse/ESSNTL-3851

    metadata:
      requirements: inv-groups-patch
      assignee: fstavela
      importance: high
      title: Update group's name to match other group's name in a different account
    """
    hosts = host_inventory.kafka.create_random_hosts(3)
    hosts_ids = {host.id for host in hosts}
    hosts_secondary = host_inventory_secondary.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)
    group_name_secondary = generate_display_name()
    group_secondary = host_inventory_secondary.apis.groups.create_group(
        group_name_secondary, hosts=hosts_secondary
    )

    response = host_inventory.apis.groups.patch_group(
        group, name=group_name_secondary, wait_for_updated=False
    )
    assert response.id == group.id
    assert response.name == group_name_secondary
    assert response.host_count == len(hosts_ids)

    host_inventory.apis.groups.verify_updated(group, name=group_name_secondary, hosts=hosts_ids)
    host_inventory_secondary.apis.groups.verify_not_updated(
        group_secondary, name=group_name_secondary, hosts=hosts_secondary
    )


@pytest.mark.ephemeral
def test_groups_patch_different_account_host(
    host_inventory: ApplicationHostInventory, host_inventory_secondary: ApplicationHostInventory
):
    """
    https://issues.redhat.com/browse/ESSNTL-3851
    https://issues.redhat.com/browse/RHINENG-21930
    https://issues.redhat.com/browse/RHINENG-18151

    metadata:
      requirements: inv-groups-patch, inv-account-integrity
      assignee: fstavela
      importance: critical
      title: Try to add hosts from different account to group via PATCH request
    """
    hosts = host_inventory.kafka.create_random_hosts(3)
    hosts_secondary = host_inventory_secondary.kafka.create_random_hosts(3)
    hosts_ids_secondary = {host.id for host in hosts_secondary}

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)

    expected_msg = ("Could not find existing host(s) with ID ", *hosts_ids_secondary)
    with raises_apierror(400, expected_msg):
        host_inventory.apis.groups.patch_group(
            group, hosts=hosts_secondary, wait_for_updated=False
        )

    host_inventory.apis.groups.verify_not_updated(group, name=group_name, hosts=hosts)
    response = host_inventory_secondary.apis.hosts.get_hosts_by_id_response(hosts_secondary)
    assert {host.id for host in response.results} == hosts_ids_secondary


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "patched_name", ["same", "different"], ids=["same name", "different name"]
)
@pytest.mark.parametrize(
    "patched_hosts",
    ["same", "my_account", "their_account"],
    ids=["same hosts", "my account hosts", "their account hosts"],
)
def test_groups_patch_group_from_different_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
    patched_name: str,
    patched_hosts: str,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3851

    metadata:
      requirements: inv-groups-patch, inv-account-integrity
      assignee: fstavela
      importance: critical
      title: Try to update a group from a different account
    """
    original_hosts = host_inventory_secondary.kafka.create_random_hosts(3)

    original_name = generate_display_name()
    group_secondary = host_inventory_secondary.apis.groups.create_group(
        original_name, hosts=original_hosts
    )

    updated_name = original_name if patched_name == "same" else generate_display_name()
    if patched_hosts == "my_account":
        updated_hosts = host_inventory.kafka.create_random_hosts(3)
    elif patched_hosts == "their_account":
        updated_hosts = host_inventory_secondary.kafka.create_random_hosts(3)
    else:
        updated_hosts = original_hosts

    with host_inventory.apis.groups.verify_group_count_not_changed():
        with host_inventory_secondary.apis.groups.verify_group_count_not_changed():
            with raises_apierror(404, "The requested URL was not found on the server."):
                host_inventory.apis.groups.patch_group(
                    group_secondary, name=updated_name, hosts=updated_hosts, wait_for_updated=False
                )

    host_inventory_secondary.apis.groups.verify_not_updated(
        group_secondary, name=original_name, hosts=original_hosts
    )


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "group_id",
    [generate_uuid(), generate_uuid().upper()],
    ids=["random uuid", "random uuid upper"],
)
def test_groups_patch_not_existing_group(host_inventory: ApplicationHostInventory, group_id: str):
    """
    https://issues.redhat.com/browse/ESSNTL-3851

    metadata:
      requirements: inv-groups-patch
      assignee: fstavela
      importance: low
      title: Try to update a not existing group
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    data = {"name": group_name, "host_ids": [host.id for host in hosts]}
    with host_inventory.apis.groups.verify_group_count_not_changed():
        with api_disabled_validation(host_inventory.apis.groups.raw_api) as api:
            with raises_apierror(404, "The requested URL was not found on the server."):
                api.api_group_patch_group_by_id(group_id, data)


@pytest.mark.ephemeral
def test_groups_patch_empty_string(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-11389

    metadata:
      requirements: inv-groups-patch
      assignee: fstavela
      importance: low
      title: Try to update a not existing group - empty string
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    data = {"name": group_name, "host_ids": [host.id for host in hosts]}
    with host_inventory.apis.groups.verify_group_count_not_changed():
        with api_disabled_validation(host_inventory.apis.groups.raw_api) as api:
            with raises_apierror(405, "Method Not Allowed"):
                api.api_group_patch_group_by_id("", data)


@pytest.mark.ephemeral
@pytest.mark.parametrize("group_id", INCORRECT_CANONICAL_UUIDS)
def test_groups_patch_validate_group_id_wrong(
    host_inventory: ApplicationHostInventory,
    group_id: Any,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3851

    metadata:
      requirements: inv-groups-patch, inv-api-validation
      assignee: fstavela
      importance: low
      title: Try to update a group with a wrong group ID
    """
    if group_id == "":
        pytest.skip("This is tested in test_groups_patch_not_existing_group")
    hosts = host_inventory.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    data = {"name": group_name, "host_ids": [host.id for host in hosts]}

    # f8c1684c-aáe7-4463-8cf4-773cc668862c
    err_msgs: tuple[str, ...]
    try:
        UUID(group_id)
    except (ValueError, AttributeError):
        if "á" in group_id:
            err_msgs = (group_id.replace("á", "\\u00e1"), " does not match ")
        else:
            err_msgs = (str(group_id), " does not match ")
    else:
        if group_id.isupper():
            pytest.skip("This is tested in test_groups_patch_not_existing_group")
        err_msgs = (f"'{group_id}' is not a 'uuid'",)

    with host_inventory.apis.groups.verify_group_count_not_changed():
        with api_disabled_validation(host_inventory.apis.groups.raw_api) as api:
            with raises_apierror(400, err_msgs):
                api.api_group_patch_group_by_id(group_id, data)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "group_name",
    [generate_string_of_length(0), generate_string_of_length(256)],
    ids=["too short", "too long"],
)
def test_groups_patch_validate_name_wrong_length(
    host_inventory: ApplicationHostInventory, group_name: str
):
    """
    https://issues.redhat.com/browse/ESSNTL-3851

    metadata:
      requirements: inv-groups-patch, inv-api-validation
      assignee: fstavela
      importance: low
      negative: true
      title: Try to update a group with the name of a wrong length
    """
    hosts = host_inventory.kafka.create_random_hosts(3)
    original_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(original_name, hosts=hosts)

    with raises_apierror(400, "{'name': ['Length must be between 1 and 255.']}"):
        host_inventory.apis.groups.patch_group(group, name=group_name, wait_for_updated=False)

    host_inventory.apis.groups.verify_not_updated(group, name=original_name, hosts=hosts)


@pytest.mark.ephemeral
@pytest.mark.parametrize("group_name", INCORRECT_STRING_VALUES)
def test_groups_patch_validate_name_wrong_type(
    host_inventory: ApplicationHostInventory, group_name: Any
):
    """
    https://issues.redhat.com/browse/ESSNTL-3851

    metadata:
      requirements: inv-groups-patch, inv-api-validation
      assignee: fstavela
      importance: low
      negative: true
      title: Try to update a group with a non-string name
    """
    hosts = host_inventory.kafka.create_random_hosts(3)
    original_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(original_name, hosts=hosts)

    with raises_apierror(400, f"{group_name} is not of type 'string' - 'name'"):
        host_inventory.apis.groups.patch_group(group, name=group_name, wait_for_updated=False)

    host_inventory.apis.groups.verify_not_updated(group, name=original_name, hosts=hosts)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "host_ids, error_type",
    [
        (generate_uuid(), "list"),
        ([[generate_uuid()]], "string"),
        ([generate_uuid()[:35]], "match"),
        ([generate_uuid() + "a"], "match"),
        ([generate_uuid().replace("-", "_")], "match"),
        ([generate_uuid().replace("-", "")], "uuid"),
        ([generate_string_of_length(36)], "match"),
        (None, "null"),
        ([None], "string"),
        (123, "list"),
        ([123], "string"),
        (False, "list"),
        ([False], "string"),
    ],
    ids=[
        "not a list",
        "list of list",
        "too short",
        "too long",
        "underscores",
        "without dashes",
        "random string",
        "None",
        "list None",
        "int",
        "list int",
        "bool",
        "list bool",
    ],
)
def test_groups_patch_validate_host_ids_wrong(
    host_inventory: ApplicationHostInventory,
    host_ids,
    error_type: str,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3851

    metadata:
      requirements: inv-groups-patch, inv-api-validation
      assignee: fstavela
      importance: low
      negative: true
      title: Try to update a group with host IDs of a wrong format
    """
    hosts = host_inventory.kafka.create_random_hosts(3)
    original_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(original_name, hosts=hosts)
    err_msgs: tuple[str, ...]
    if error_type == "list":
        err_msgs = (str(host_ids), " is not of type 'array' - 'host_ids'")
    elif error_type == "string":
        err_msgs = (str(host_ids[0]), " is not of type 'string' - 'host_ids.0'")
    elif error_type == "uuid":
        err_msgs = (f"'{host_ids[0]}' is not a 'uuid' - 'host_ids.0'",)
    elif error_type == "null":
        err_msgs = ("{'host_ids': ['Field may not be null.']}",)
    else:
        host_ids[0] = host_ids[0].replace("'", "").replace('"', "").replace("\\", "")
        err_msgs = (f"'{host_ids[0]}' does not match", " - 'host_ids.0'")

    data = {"host_ids": host_ids}

    with raises_apierror(400, err_msgs):
        host_inventory.apis.groups.raw_api.api_group_patch_group_by_id(group.id, data)

    host_inventory.apis.groups.verify_not_updated(group, name=original_name, hosts=hosts)


@pytest.mark.ephemeral
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
def test_groups_patch_validate_protected_fields(
    host_inventory: ApplicationHostInventory, field: str, value: str
):
    """
    https://issues.redhat.com/browse/ESSNTL-3851

    metadata:
      requirements: inv-groups-patch, inv-api-validation
      assignee: fstavela
      importance: medium
      negative: true
      title: Try to update a group with changing protected fields
    """
    hosts = host_inventory.kafka.create_random_hosts(3)
    original_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(original_name, hosts=hosts)

    data = {"name": generate_display_name(), field: value}
    with raises_apierror(400, f"{{'{field}': ['Unknown field.']}}"):
        host_inventory.apis.groups.raw_api.api_group_patch_group_by_id(group.id, data)

    host_inventory.apis.groups.verify_not_updated(group, name=original_name, hosts=hosts)


@pytest.mark.ephemeral
@pytest.mark.parametrize("org_id", ["same", "different"])
def test_groups_patch_with_changed_org_id(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
    hbi_default_org_id: str,
    hbi_secondary_org_id: str,
    org_id: str,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3851

    metadata:
      requirements: inv-groups-patch, inv-api-validation
      assignee: fstavela
      importance: high
      negative: true
      title: Try to update a group with changing the org_id
    """
    hosts = host_inventory.kafka.create_random_hosts(3)
    original_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(original_name, hosts=hosts)

    value = hbi_default_org_id if org_id == "same" else hbi_secondary_org_id
    data = {"name": generate_display_name(), "org_id": value}
    with host_inventory_secondary.apis.groups.verify_group_count_not_changed():
        with raises_apierror(400, "{'org_id': ['Unknown field.']}"):
            host_inventory.apis.groups.raw_api.api_group_patch_group_by_id(group.id, data)

    host_inventory.apis.groups.verify_not_updated(group, name=original_name, hosts=hosts)


@pytest.mark.ephemeral
def test_groups_patch_with_random_field(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-3851

    metadata:
      requirements: inv-groups-patch, inv-api-validation
      assignee: fstavela
      importance: low
      negative: true
      title: Try to update a group with adding new field
    """
    hosts = host_inventory.kafka.create_random_hosts(3)
    original_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(original_name, hosts=hosts)

    data = {"name": generate_display_name(), "field123": "value123"}
    with raises_apierror(400, "{'field123': ['Unknown field.']}"):
        host_inventory.apis.groups.raw_api.api_group_patch_group_by_id(group.id, data)

    host_inventory.apis.groups.verify_not_updated(group, name=original_name, hosts=hosts)


@pytest.mark.ephemeral
@pytest.mark.parametrize("data", [None, {}], ids=["None", "empty dict"])
def test_groups_patch_without_data(host_inventory: ApplicationHostInventory, data: dict | None):
    """
    https://issues.redhat.com/browse/ESSNTL-3851

    metadata:
      requirements: inv-groups-patch, inv-api-validation
      assignee: fstavela
      importance: low
      negative: true
      title: Try to update a group without sending any data
    """
    hosts = host_inventory.kafka.create_random_hosts(3)
    original_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(original_name, hosts=hosts)

    err_msg = "RequestBody is required" if data is None else "Patch json document cannot be empty."
    with api_disabled_validation(host_inventory.apis.groups.raw_api) as api:
        with raises_apierror(400, err_msg):
            api.api_group_patch_group_by_id(group.id, data)

    host_inventory.apis.groups.verify_not_updated(group, name=original_name, hosts=hosts)


def test_groups_patch_strip_whitespace(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-3108

    metadata:
      requirements: inv-groups-patch
      assignee: fstavela
      importance: medium
      negative: true
      title: Test that Inventory strips a group name from whitespaces when patching a group
    """
    group1 = host_inventory.apis.groups.create_group(generate_display_name())

    new_name = " " + generate_display_name() + " "
    stripped_name = new_name.strip()

    updated_group = host_inventory.apis.groups.patch_group(
        group1, name=new_name, wait_for_updated=False
    )
    assert updated_group.name == stripped_name
    host_inventory.apis.groups.verify_updated(group1, name=stripped_name)


@pytest.mark.ephemeral
def test_groups_patch_with_the_same_host_multiple_times(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/RHINENG-10846
    https://issues.redhat.com/browse/RHINENG-10845

    metadata:
      requirements: inv-groups-patch
      assignee: fstavela
      importance: low
      negative: true
      title: Try to update a group with the same Host ID multiple times in the data
    """
    host = host_inventory.kafka.create_host()
    group = host_inventory.apis.groups.create_group(generate_display_name())
    with raises_apierror(400, "Host IDs must be unique."):
        host_inventory.apis.groups.patch_group(
            group, name=generate_display_name(), hosts=[host.id, host.id], wait_for_updated=False
        )

    host_inventory.apis.groups.verify_not_updated(group, name=group.name)

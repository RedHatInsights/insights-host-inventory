from __future__ import annotations

import logging

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import generate_display_name

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)


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
def test_groups_patch_two_groups_same_hosts(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-3851

    metadata:
      assignee: fstavela
      importance: high
      title: Update group's hosts to match hosts of other group (move allowed)
    """
    hosts = host_inventory.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts[:2])
    group_name2 = generate_display_name()
    group2 = host_inventory.apis.groups.create_group(group_name2, hosts=hosts[2:])

    # Patching group2 to include all hosts moves hosts[0] and hosts[1] from group to group2
    response = host_inventory.apis.groups.patch_group(group2, hosts=hosts, wait_for_updated=False)
    assert response.id == group2.id
    assert response.host_count == 3

    host_inventory.apis.groups.verify_updated(group2, name=group_name2, hosts=hosts)
    # group1 should now have no hosts (they were moved to group2)
    host_inventory.apis.groups.verify_updated(group, name=group_name, hosts=[])


@pytest.mark.ephemeral
def test_groups_patch_different_account_name(
    host_inventory: ApplicationHostInventory, host_inventory_secondary: ApplicationHostInventory
):
    """
    https://issues.redhat.com/browse/ESSNTL-3851

    metadata:
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

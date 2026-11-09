from __future__ import annotations

import logging

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_sp_field_value
from iqe_host_inventory.utils.datagen_utils import get_sp_field_by_name

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)


@pytest.mark.parametrize("hosts_list", [[], None], ids=["empty list", "not present"])
def test_groups_create_empty(host_inventory, hosts_list):
    """
    https://issues.redhat.com/browse/ESSNTL-3828

    metadata:
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


def test_groups_create_with_one_host(host_inventory: ApplicationHostInventory):
    """
    https://issues.redhat.com/browse/ESSNTL-3828
    https://issues.redhat.com/browse/RHINENG-8990

    metadata:
      assignee: fstavela
      importance: high
      title: Create a group with one host
    """
    host = host_inventory.upload.create_host()

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=host, wait_for_created=False)
    assert group.id
    assert group.name == group_name
    assert group.host_count == 1
    host_inventory.apis.groups.verify_updated(group, name=group_name, hosts=host)


@pytest.mark.ephemeral
@pytest.mark.parametrize("host_type", ["conventional", "edge", "image-mode", "all"])
def test_groups_create_with_multiple_hosts(
    host_inventory: ApplicationHostInventory, host_type: str
):
    """
    https://issues.redhat.com/browse/ESSNTL-3828
    https://issues.redhat.com/browse/RHINENG-8990

    metadata:
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
def test_groups_create_different_account_name(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3828

    metadata:
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

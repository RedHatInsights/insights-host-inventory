import logging

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.api_utils import is_ungrouped_host
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.datagen_utils import generate_sp_field_value
from iqe_host_inventory.utils.datagen_utils import get_sp_field_by_name

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)


@pytest.mark.ephemeral
@pytest.mark.parametrize("how_many", [1, 3], ids=["add single host", "add multiple hosts"])
@pytest.mark.parametrize("with_hosts", [False, True], ids=["empty", "with hosts"])
@pytest.mark.parametrize("host_type", ["conventional", "edge", "image-mode"])
def test_groups_add_hosts(
    host_inventory: ApplicationHostInventory,
    how_many: int,
    with_hosts: bool,
    host_type: str,
):
    """
    https://issues.redhat.com/browse/ESSNTL-4377

    metadata:
      assignee: fstavela
      importance: high
      title: Add hosts to group via POST request
    """
    sp_bootc = get_sp_field_by_name("bootc_status")
    hosts_data = host_inventory.datagen.create_n_hosts_data(4)

    if host_type == "edge":
        for i in range(1, 4):
            hosts_data[i]["system_profile"]["host_type"] = "edge"
    if host_type == "image-mode":
        for i in range(1, 4):
            hosts_data[i]["system_profile"]["bootc_status"] = generate_sp_field_value(sp_bootc)

    hosts = host_inventory.kafka.create_hosts(hosts_data=hosts_data)

    group_name = generate_display_name()
    pre_added_hosts = [hosts[0]] if with_hosts else []
    group = host_inventory.apis.groups.create_group(group_name, hosts=pre_added_hosts)

    hosts_to_add = hosts[1 : 1 + how_many]
    expected_hosts_ids = {host.id for host in pre_added_hosts + hosts_to_add}
    response = host_inventory.apis.groups.add_hosts_to_group(
        group, hosts_to_add, wait_for_added=False
    )
    assert response.id == group.id
    assert response.name == group_name
    assert response.host_count == len(expected_hosts_ids)

    host_inventory.apis.groups.verify_updated(group, name=group_name, hosts=expected_hosts_ids)


@pytest.mark.ephemeral
def test_groups_add_hosts_from_different_account(
    host_inventory: ApplicationHostInventory, host_inventory_secondary: ApplicationHostInventory
):
    """
    https://issues.redhat.com/browse/ESSNTL-4377

    metadata:
      assignee: fstavela
      importance: critical
      negative: true
      title: Try to add hosts from different account to group via POST request
    """
    hosts = host_inventory.kafka.create_random_hosts(3)
    hosts_secondary = host_inventory_secondary.kafka.create_random_hosts(3)
    hosts_ids_secondary = {host.id for host in hosts_secondary}

    group_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(group_name, hosts=hosts)

    with raises_apierror(400, ("Could not find existing host(s) with ID ", *hosts_ids_secondary)):
        host_inventory.apis.groups.add_hosts_to_group(
            group, hosts=hosts_secondary, wait_for_added=False
        )

    host_inventory.apis.groups.verify_not_updated(group, name=group_name, hosts=hosts)
    response = host_inventory_secondary.apis.hosts.get_hosts_by_id_response(hosts_secondary)
    assert {host.id for host in response.results} == hosts_ids_secondary
    for host in response.results:
        assert is_ungrouped_host(host)


@pytest.mark.ephemeral
@pytest.mark.parametrize(
    "added_hosts",
    ["same", "my_account", "their_account"],
    ids=["same hosts", "my account hosts", "their account hosts"],
)
def test_groups_add_hosts_to_different_account_group(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
    added_hosts: str,
):
    """
    https://issues.redhat.com/browse/ESSNTL-4377

    metadata:
      assignee: fstavela
      importance: critical
      negative: true
      title: Try to add hosts to a group from a different account
    """
    original_hosts = host_inventory_secondary.kafka.create_random_hosts(3)

    group_name = generate_display_name()
    group_secondary = host_inventory_secondary.apis.groups.create_group(
        group_name, hosts=original_hosts
    )

    if added_hosts == "my_account":
        updated_hosts = host_inventory.kafka.create_random_hosts(3)
    elif added_hosts == "their_account":
        updated_hosts = host_inventory_secondary.kafka.create_random_hosts(3)
    else:
        updated_hosts = original_hosts

    with host_inventory.apis.groups.verify_group_count_not_changed():
        with host_inventory_secondary.apis.groups.verify_group_count_not_changed():
            with raises_apierror(404):
                host_inventory.apis.groups.add_hosts_to_group(
                    group_secondary, hosts=updated_hosts, wait_for_added=False
                )

    host_inventory_secondary.apis.groups.verify_not_updated(
        group_secondary, name=group_name, hosts=original_hosts
    )


@pytest.mark.ephemeral
@pytest.mark.parametrize("org_id", ["same", "different"])
def test_groups_add_hosts_with_changed_org_id(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
    hbi_default_org_id: str,
    hbi_secondary_org_id: str,
    org_id: str,
):
    """
    https://issues.redhat.com/browse/ESSNTL-4377

    metadata:
      assignee: fstavela
      importance: high
      negative: true
      title: Try to add hosts to a group with changing the org_id
    """
    hosts = host_inventory.kafka.create_random_hosts(3)
    original_name = generate_display_name()
    group = host_inventory.apis.groups.create_group(original_name, hosts=hosts)

    value = hbi_default_org_id if org_id == "same" else hbi_secondary_org_id
    data = {"org_id": value}
    with host_inventory_secondary.apis.groups.verify_group_count_not_changed():
        with raises_apierror(400, f"{data} is not of type 'array'"):
            host_inventory.apis.groups.raw_api.api_host_group_add_host_list_to_group(
                group.id, data
            )

    host_inventory.apis.groups.verify_not_updated(group, name=original_name, hosts=hosts)

import logging

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.groups_api import GroupData
from iqe_host_inventory.tests.rest.groups.test_groups_get_by_id import in_order
from iqe_host_inventory.utils.datagen_utils import generate_display_name

pytestmark = [pytest.mark.backend]
logger = logging.getLogger(__name__)


def test_groups_get_list_no_groups(host_inventory: ApplicationHostInventory):
    """WARNING: Don't run this test in shared accounts. It deletes all groups on account.

    https://issues.redhat.com/browse/ESSNTL-3829

    metadata:
      assignee: fstavela
      importance: high
      title: Get groups list when there are no groups
    """
    host_inventory.apis.groups.delete_all_groups()

    response = host_inventory.apis.groups.get_groups_response()

    # If Kessel is bypassed, the response is empty. Otherwise, we see the default workspace.
    assert response.total <= 1
    assert response.count <= 1
    assert response.page == 1
    assert len(response.results) <= 1
    if response.results:
        assert response.results[0].name == "Default Workspace"


@pytest.mark.ephemeral
@pytest.mark.parametrize("n_hosts", [0, 1, 3])
@pytest.mark.parametrize("n_groups", [1, 3])
def test_groups_get_list(
    host_inventory: ApplicationHostInventory,
    n_hosts: int,
    n_groups: int,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3829

    metadata:
      assignee: fstavela
      importance: high
      title: Get groups list
    """
    hosts = host_inventory.kafka.create_random_hosts(9)

    groups_data = [
        GroupData(hosts=hosts[(i * n_hosts) : (i * n_hosts + n_hosts)]) for i in range(n_groups)
    ]
    host_inventory.apis.groups.create_groups(groups_data)

    response = host_inventory.apis.groups.get_groups_response()
    assert response.total >= n_groups
    assert response.count >= n_groups
    assert response.page == 1
    assert len(response.results) >= n_groups


@pytest.mark.ephemeral
@pytest.mark.parametrize("order_by", ["name", "host_count", "updated"])
@pytest.mark.parametrize("order_how", ["ASC", "DESC"])
def test_groups_get_list_ordering_and_pagination(
    host_inventory,
    setup_groups_for_ordering,
    order_by,
    order_how,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3829

    metadata:
      assignee: fstavela
      importance: high
      title: Get groups list - paginate through ordered results (RBAC v1 only)

    NOTE: order_how (ASC/DESC) is only supported in RBAC v1 (database).
    RBAC v2 does not handle order_how.
    """

    found_groups = []
    for i in range(3):
        response = host_inventory.apis.groups.get_groups_response(
            per_page=3, page=i + 1, order_how=order_how, order_by=order_by
        )
        assert response.page == i + 1
        assert response.per_page == 3
        assert response.total >= 10
        assert response.count == 3
        assert len(response.results) == 3
        found_groups += response.results

    assert len({group.id for group in found_groups}) == 9
    assert in_order(found_groups, None, ascending=(order_how == "ASC"), sort_field=order_by)


@pytest.mark.parametrize(
    "case_insensitive", [True, False], ids=["case insensitive", "case sensitive"]
)
def test_groups_get_list_by_name_part(host_inventory, case_insensitive):
    """
    https://issues.redhat.com/browse/ESSNTL-3829

    metadata:
      assignee: fstavela
      importance: high
      title: Get groups list by name - provide only part of the name
    """
    groups_data = [GroupData(name=generate_display_name("filtering"), hosts=[]) for _ in range(3)]
    groups = host_inventory.apis.groups.create_groups(groups_data)
    groups += host_inventory.apis.groups.create_n_empty_groups(3)
    wanted_groups_dict = {group.id: group for group in groups[:3]}

    searched_name = "ILTERIN" if case_insensitive else "ilterin"
    response = host_inventory.apis.groups.get_groups_response(name=searched_name)
    assert response.count == 3
    assert response.total == 3
    assert response.page == 1
    assert len(response.results) == 3
    assert {group.id for group in response.results} == set(wanted_groups_dict.keys())
    for group in response.results:
        assert group == wanted_groups_dict[group.id]


@pytest.mark.ephemeral
@pytest.mark.parametrize("with_hosts", [True, False], ids=["with hosts", "without hosts"])
def test_groups_get_list_different_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
    hbi_default_org_id: str,
    with_hosts: bool,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3829

    metadata:
      assignee: fstavela
      importance: critical
      negative: true
      title: Get groups list - check I can't get group from different account
    """
    hosts_primary = host_inventory.kafka.create_random_hosts(3)
    hosts_secondary = host_inventory_secondary.kafka.create_random_hosts(3)

    groups_data_primary = [
        GroupData(hosts=[hosts_primary[i]] if with_hosts else []) for i in range(3)
    ]
    groups_data_secondary = [
        GroupData(hosts=[hosts_secondary[i]] if with_hosts else []) for i in range(3)
    ]
    host_inventory.apis.groups.create_groups(groups_data_primary)
    host_inventory_secondary.apis.groups.create_groups(groups_data_secondary)

    response = host_inventory.apis.groups.get_groups_response()
    assert response.count >= 3
    assert response.total >= 3
    assert response.page == 1
    assert len(response.results) >= 3
    for group in response.results:
        assert group.org_id == hbi_default_org_id


@pytest.mark.ephemeral
@pytest.mark.parametrize("with_hosts", [True, False], ids=["with hosts", "without hosts"])
def test_groups_get_list_by_name_different_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
    with_hosts: bool,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3829

    metadata:
      assignee: fstavela
      importance: critical
      negative: true
      title: Get groups list by name - try to get group from different account
    """
    hosts_primary = host_inventory.kafka.create_random_hosts(3)
    hosts_secondary = host_inventory_secondary.kafka.create_random_hosts(3)

    groups_data_primary = [
        GroupData(hosts=[hosts_primary[i]] if with_hosts else []) for i in range(3)
    ]
    groups_data_secondary = [
        GroupData(hosts=[hosts_secondary[i]] if with_hosts else []) for i in range(3)
    ]
    host_inventory.apis.groups.create_groups(groups_data_primary)
    groups_secondary = host_inventory_secondary.apis.groups.create_groups(groups_data_secondary)

    response = host_inventory.apis.groups.get_groups_response(name=groups_secondary[1].name)
    assert response.count == 0
    assert response.total == 0
    assert response.page == 1
    assert response.results == []


@pytest.mark.ephemeral
@pytest.mark.parametrize("with_hosts", [True, False], ids=["with hosts", "without hosts"])
def test_groups_get_list_by_name_my_and_different_account(
    host_inventory: ApplicationHostInventory,
    host_inventory_secondary: ApplicationHostInventory,
    with_hosts: bool,
):
    """
    https://issues.redhat.com/browse/ESSNTL-3829

    metadata:
      assignee: fstavela
      importance: critical
      negative: true
      title: Get groups list by name - try to get group from my and different account
    """
    hosts_primary = host_inventory.kafka.create_random_hosts(3)
    hosts_secondary = host_inventory_secondary.kafka.create_random_hosts(3)

    groups_data_primary = [
        GroupData(name=generate_display_name(), hosts=[hosts_primary[i]] if with_hosts else [])
        for i in range(3)
    ]
    groups_data_secondary = [
        GroupData(
            name=groups_data_primary[i].name, hosts=([hosts_secondary[i]] if with_hosts else [])
        )
        for i in range(3)
    ]
    groups_primary = host_inventory.apis.groups.create_groups(groups_data_primary)
    groups_secondary = host_inventory_secondary.apis.groups.create_groups(groups_data_secondary)

    response = host_inventory.apis.groups.get_groups_response(name=groups_secondary[1].name)
    assert response.count == 1
    assert response.total == 1
    assert response.page == 1
    assert len(response.results) == 1
    assert response.results[0] == groups_primary[1]

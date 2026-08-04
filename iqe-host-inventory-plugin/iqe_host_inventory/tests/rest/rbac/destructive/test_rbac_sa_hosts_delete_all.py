# mypy: disallow-untyped-defs

"""
These tests delete all hosts on the account,
that's why they have to be in a separate module (file).
Otherwise, they would be messing with hosts needed for other tests.
"""

import logging

import pytest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory_api import GroupOutWithHostCount
from iqe_host_inventory_api import HostOut

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.backend, pytest.mark.rbac_dependent, pytest.mark.service_account]


@pytest.fixture(scope="module")
def prepare_groups(host_inventory: ApplicationHostInventory) -> list[GroupOutWithHostCount]:
    return host_inventory.apis.groups.create_n_empty_groups(3, cleanup_scope="module")


@pytest.fixture(scope="function")
def prepare_hosts(
    host_inventory: ApplicationHostInventory,
    prepare_groups: list[GroupOutWithHostCount],
) -> list[HostOut]:
    hosts = host_inventory.upload.create_hosts(4)
    host_inventory.apis.groups.add_hosts_to_group(prepare_groups[0], hosts[0])
    host_inventory.apis.groups.add_hosts_to_group(prepare_groups[1], hosts[1])
    host_inventory.apis.groups.add_hosts_to_group(prepare_groups[2], hosts[2])
    return hosts


@pytest.mark.usefixtures("prepare_hosts")
def test_rbac_sa_hosts_write_permission_delete_hosts_all(
    host_inventory_sa_1: ApplicationHostInventory,
    host_inventory: ApplicationHostInventory,
) -> None:
    """
    JIRA: https://issues.redhat.com/browse/RHINENG-7891

    metadata:
        requirements: inv-rbac, inv-hosts-delete-all
        assignee: fstavela
        importance: high
        title: Test that service accounts with "hosts:write" permission can delete all hosts
    """
    host_inventory_sa_1.apis.hosts.confirm_delete_all()
    host_inventory.apis.hosts.verify_all_deleted()


def test_rbac_sa_hosts_no_write_permission_delete_hosts_all(
    prepare_hosts: list[HostOut],
    host_inventory_sa_2: ApplicationHostInventory,
    host_inventory: ApplicationHostInventory,
) -> None:
    """
    JIRA: https://issues.redhat.com/browse/RHINENG-7891

    metadata:
        requirements: inv-rbac, inv-hosts-delete-all
        assignee: fstavela
        importance: high
        negative: true
        title: Test that service accounts without "hosts:write" permission can't delete all hosts
    """
    with raises_apierror(
        403,
        "You don't have the permission to access the requested resource. "
        "It is either read-protected or not readable by the server.",
    ):
        host_inventory_sa_2.apis.hosts.raw_api.api_host_delete_all_hosts(confirm_delete_all=True)

    host_inventory.apis.hosts.verify_not_deleted(prepare_hosts)

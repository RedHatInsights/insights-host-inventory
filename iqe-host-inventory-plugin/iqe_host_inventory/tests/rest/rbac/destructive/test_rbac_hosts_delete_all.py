# mypy: disallow-untyped-defs

"""
These tests delete all hosts on the account,
that's why they have to be in a separate module (file).
Otherwise, they would be messing with hosts needed for other tests.
"""

import logging
from collections.abc import Callable
from os import getenv

import pytest
from pytest_lazy_fixtures import lf

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.api_utils import raises_apierror
from iqe_host_inventory.utils.rbac_utils import RBACInventoryPermission
from iqe_host_inventory_api import GroupOutWithHostCount
from iqe_host_inventory_api import HostOut

logger = logging.getLogger(__name__)


pytestmark = [pytest.mark.backend, pytest.mark.rbac_dependent]


@pytest.fixture(
    params=[
        lf("host_inventory_rbac_inv_admin"),
        lf("host_inventory_rbac_hosts_admin"),
        lf("host_inventory_rbac_hosts_write"),
        lf("host_inventory_rbac_hosts_all"),
    ],
)
def host_inventory_write_permissions(
    request: pytest.FixtureRequest,
) -> ApplicationHostInventory:
    return request.param


@pytest.fixture(
    params=[
        lf("host_inventory_rbac_groups_admin"),
        lf("host_inventory_rbac_groups_viewer"),
        lf("host_inventory_rbac_groups_write"),
        lf("host_inventory_rbac_groups_all"),
        lf("host_inventory_rbac_hosts_viewer"),
        lf("host_inventory_rbac_all_read"),
        lf("host_inventory_rbac_no_perms"),
    ],
)
def host_inventory_no_write_permissions(
    request: pytest.FixtureRequest,
) -> ApplicationHostInventory:
    return request.param


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


@pytest.fixture(scope="module")
def prepare_hosts_module(
    host_inventory: ApplicationHostInventory, prepare_groups: list[GroupOutWithHostCount]
) -> list[HostOut]:
    """Only use once! This is module scoped. If the hosts get deleted, they won't be recreated"""
    hosts = host_inventory.upload.create_hosts(4, cleanup_scope="module")
    host_inventory.apis.groups.add_hosts_to_group(prepare_groups[0], hosts[0])
    host_inventory.apis.groups.add_hosts_to_group(prepare_groups[1], hosts[1])
    host_inventory.apis.groups.add_hosts_to_group(prepare_groups[2], hosts[2])
    return hosts


@pytest.mark.usefixtures("prepare_hosts")
def test_rbac_hosts_write_permission_delete_hosts_all(
    host_inventory: ApplicationHostInventory,
    host_inventory_write_permissions: ApplicationHostInventory,
) -> None:
    """
    https://issues.redhat.com/browse/ESSNTL-2218

    metadata:

        assignee: fstavela
        importance: high
        title: Test that users with "hosts:write" permission can delete all hosts
    """
    host_inventory_write_permissions.apis.hosts.delete_all(confirm_delete_all=True)
    host_inventory.apis.hosts.verify_all_deleted()


def test_rbac_hosts_no_write_permission_delete_hosts_all(
    host_inventory: ApplicationHostInventory,
    host_inventory_no_write_permissions: ApplicationHostInventory,
    prepare_hosts_module: list[HostOut],
) -> None:
    """
    https://issues.redhat.com/browse/ESSNTL-2218

    metadata:

        assignee: fstavela
        importance: high
        negative: true
        title: Test that users without "hosts:write" permission can't delete all hosts
    """
    with raises_apierror(
        403,
        "You don't have the permission to access the requested resource. "
        "It is either read-protected or not readable by the server.",
    ):
        host_inventory_no_write_permissions.apis.hosts.delete_all(confirm_delete_all=True)

    host_inventory.apis.hosts.verify_not_deleted(prepare_hosts_module)


@pytest.mark.skipif(
    getenv("ENV_FOR_DYNACONF", "stage_proxy").lower() == "clowder_smoke",
    reason="RBAC ignores HBI groups if RBAC V2 (Kessel) is disabled: "
    "https://redhat-internal.slack.com/archives/C0233N2MBU6/p1755699688749819",
    # TODO: Remove skipif when https://issues.redhat.com/browse/RHCLOUD-41427 is done
)
def test_rbac_granular_hosts_write_permission_delete_hosts_all(
    hbi_non_org_admin_user_rbac_setup: Callable,
    host_inventory: ApplicationHostInventory,
    host_inventory_non_org_admin: ApplicationHostInventory,
    prepare_hosts: list[HostOut],
    prepare_groups: list[GroupOutWithHostCount],
) -> None:
    """
    https://issues.redhat.com/browse/ESSNTL-2218
    https://issues.redhat.com/browse/ESSNTL-4961

    metadata:

        assignee: fstavela
        importance: high
        title: Test that users with granular RBAC access can delete all hosts (only correct ones)
    """
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.HOSTS_WRITE], hbi_groups=prepare_groups[:2]
    )

    host_inventory_non_org_admin.apis.hosts.delete_all(confirm_delete_all=True)
    host_inventory.apis.hosts.wait_for_deleted(prepare_hosts[:2])
    host_inventory.apis.hosts.verify_not_deleted(prepare_hosts[2:])

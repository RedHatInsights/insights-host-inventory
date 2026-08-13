from __future__ import annotations

import logging
from collections.abc import Generator
from typing import NamedTuple

import pytest
from _pytest.fixtures import FixtureRequest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.groups_api import GROUP_OR_ID
from iqe_host_inventory.utils.rbac_utils import RBACInventoryPermission
from iqe_host_inventory.utils.rbac_utils import RBACRoles
from iqe_host_inventory.utils.rbac_utils import get_role_id
from iqe_host_inventory.utils.rbac_utils import wait_for_kessel_sync
from iqe_host_inventory_api import GroupOutWithHostCount
from iqe_host_inventory_api import HostOut
from iqe_host_inventory_api import StructuredTag

RBAC_GROUP_SERVICE_ACCOUNT_REGULAR = "ServiceAccountRegular"

logger = logging.getLogger(__name__)


@pytest.fixture(scope="function")
def hbi_non_org_admin_user_rbac_setup(
    host_inventory: ApplicationHostInventory, hbi_non_org_admin_user_username: str
):
    """
    Fixture to create a Group, Role for giving a
    specific inventory permission to a user
    """
    to_delete: list[tuple[str, list[str]]] = []

    def _rbac_inventory_user_setup(
        permissions: list[RBACInventoryPermission],
        hbi_groups: list[GROUP_OR_ID | None] | None = None,
    ) -> None:
        group, roles = host_inventory.apis.rbac.setup_rbac_user(
            hbi_non_org_admin_user_username, permissions, hbi_groups=hbi_groups
        )

        to_delete.append((group.uuid, [get_role_id(role) for role in roles]))

    yield _rbac_inventory_user_setup

    for rbac_setup in to_delete:
        for role_id in rbac_setup[1]:
            host_inventory.apis.rbac.delete_role(role_id)
        host_inventory.apis.rbac.delete_group(rbac_setup[0])


@pytest.fixture(scope="class")
def hbi_non_org_admin_user_rbac_setup_class(
    host_inventory: ApplicationHostInventory,
    hbi_non_org_admin_user_username: str,
):
    """
    Fixture to create a Group, Role for giving a
    specific inventory permission to a user
    """
    to_delete: list[tuple[str, list[str]]] = []

    def _rbac_inventory_user_setup(
        permissions: list[RBACInventoryPermission],
        hbi_groups: list[GROUP_OR_ID | None] | None = None,
        expected_hbi_groups: list[GROUP_OR_ID | None] | None = None,
    ) -> None:
        group, roles = host_inventory.apis.rbac.setup_rbac_user(
            hbi_non_org_admin_user_username, permissions, hbi_groups=hbi_groups
        )
        to_delete.append((group.uuid, [get_role_id(role) for role in roles]))

    yield _rbac_inventory_user_setup

    for rbac_setup in to_delete:
        for role_id in rbac_setup[1]:
            host_inventory.apis.rbac.delete_role(role_id)
        host_inventory.apis.rbac.delete_group(rbac_setup[0])


@pytest.fixture(scope="class")
def rbac_non_org_admin_rbac_admin_setup_class(
    host_inventory: ApplicationHostInventory,
    host_inventory_non_org_admin: ApplicationHostInventory,
    hbi_non_org_admin_user_username: str,
) -> Generator[ApplicationHostInventory]:
    """
    Fixture to create a Group, Role for giving an 'rbac:*:*' permission to a user
    """
    host_inventory.apis.rbac.reset_user_groups(hbi_non_org_admin_user_username)

    group = host_inventory.apis.rbac.create_group(RBACInventoryPermission.RBAC_ADMIN)
    host_inventory.apis.rbac.add_user_to_a_group(hbi_non_org_admin_user_username, group.uuid)

    role = host_inventory.apis.rbac.get_rbac_admin_role()
    if host_inventory.unleash.is_rbac_workspaces_enabled:
        workspace_id = host_inventory.apis.workspaces.default_workspace.id
        host_inventory.apis.rbac.create_role_bindings(
            [get_role_id(role)], group.uuid, [workspace_id]
        )
    else:
        host_inventory.apis.rbac.add_roles_to_a_group([role], group.uuid)

    wait_for_kessel_sync(host_inventory)

    yield host_inventory_non_org_admin

    host_inventory.apis.rbac.delete_group(group.uuid)


@pytest.fixture(scope="class")
def rbac_inventory_admin_user_setup_class(hbi_non_org_admin_user_rbac_setup_class):
    hbi_non_org_admin_user_rbac_setup_class(permissions=[RBACInventoryPermission.ADMIN])


@pytest.fixture(scope="class")
def rbac_inventory_hosts_read_granular_user_setup_class(
    rbac_setup_resources: RBACResources, hbi_non_org_admin_user_rbac_setup_class
) -> RBACResources:
    hbi_non_org_admin_user_rbac_setup_class(
        permissions=[RBACInventoryPermission.HOSTS_READ],
        hbi_groups=rbac_setup_resources.groups[:2],
    )
    return rbac_setup_resources


@pytest.fixture(scope="class")
def rbac_inventory_groups_read_granular_user_setup_class(
    rbac_setup_resources: RBACResources, hbi_non_org_admin_user_rbac_setup_class
) -> RBACResources:
    hbi_non_org_admin_user_rbac_setup_class(
        permissions=[RBACInventoryPermission.GROUPS_READ],
        hbi_groups=rbac_setup_resources.groups[:2],
    )
    return rbac_setup_resources


@pytest.fixture(scope="class")
def rbac_inventory_hosts_write_granular_user_setup_class(
    rbac_setup_resources: RBACResources, hbi_non_org_admin_user_rbac_setup_class
) -> RBACResources:
    hbi_non_org_admin_user_rbac_setup_class(
        permissions=[RBACInventoryPermission.HOSTS_WRITE],
        hbi_groups=rbac_setup_resources.groups[:2],
    )
    return rbac_setup_resources


@pytest.fixture(scope="class")
def rbac_inventory_groups_write_granular_user_setup_class(
    rbac_setup_resources: RBACResources, hbi_non_org_admin_user_rbac_setup_class
) -> RBACResources:
    hbi_non_org_admin_user_rbac_setup_class(
        permissions=[RBACInventoryPermission.GROUPS_WRITE],
        hbi_groups=rbac_setup_resources.groups[:2],
    )
    return rbac_setup_resources


@pytest.fixture(scope="class")
def rbac_inventory_groups_all_granular_user_setup_class(
    rbac_setup_resources: RBACResources, hbi_non_org_admin_user_rbac_setup_class
) -> RBACResources:
    hbi_non_org_admin_user_rbac_setup_class(
        permissions=[RBACInventoryPermission.GROUPS_ALL],
        hbi_groups=rbac_setup_resources.groups[:2],
    )
    return rbac_setup_resources


@pytest.fixture(scope="class")
def rbac_inventory_user_without_permissions_setup_class(
    host_inventory: ApplicationHostInventory,
    hbi_non_org_admin_user_username: str,
):
    host_inventory.apis.rbac.reset_user_groups(hbi_non_org_admin_user_username)
    wait_for_kessel_sync(host_inventory)


@pytest.fixture(scope="class")
def rbac_staleness_all_hosts_all_user_setup_class(
    hbi_non_org_admin_user_rbac_setup_class,
):
    hbi_non_org_admin_user_rbac_setup_class(
        permissions=[RBACInventoryPermission.STALENESS_ALL, RBACInventoryPermission.HOSTS_ALL]
    )


class RBACResources(NamedTuple):
    hosts: list[list[HostOut]]
    tags: list[list[list[StructuredTag]]]
    groups: list[GroupOutWithHostCount]


@pytest.fixture(scope="class")
def rbac_hosts_read_advisor_read_user_setup_class(hbi_non_org_admin_user_rbac_setup_class):
    hbi_non_org_admin_user_rbac_setup_class(
        permissions=[RBACInventoryPermission.HOSTS_READ, RBACInventoryPermission.ADVISOR_READ]
    )


@pytest.fixture(scope="class")
def rbac_hosts_read_all_services_user_setup_class(
    host_inventory: ApplicationHostInventory,
    hbi_non_org_admin_user_rbac_setup_class,
):
    hbi_non_org_admin_user_rbac_setup_class(
        permissions=[
            RBACInventoryPermission.HOSTS_READ,
            RBACInventoryPermission.ADVISOR_READ,
            RBACInventoryPermission.VULNERABILITY_READ,
            RBACInventoryPermission.COMPLIANCE_READ,
            RBACInventoryPermission.PATCH_READ,
            RBACInventoryPermission.REMEDIATIONS_READ,
        ]
    )
    role = host_inventory.apis.rbac.get_role_by_name("Malware detection viewer")
    group = host_inventory.apis.rbac.raw_api.group_api.list_groups(name="iqe-hbi").data[0]
    host_inventory.apis.rbac.add_roles_to_a_group([role], group.uuid)
    wait_for_kessel_sync(host_inventory)


@pytest.fixture(scope="module")
def rbac_clean_service_account_regular_group(host_inventory: ApplicationHostInventory):
    group = host_inventory.apis.rbac.get_group_by_name(RBAC_GROUP_SERVICE_ACCOUNT_REGULAR)
    roles = host_inventory.apis.rbac.raw_api.group_api.list_roles_for_group(group.uuid).data
    if roles:
        roles_string = ",".join([role.uuid for role in roles])
        host_inventory.apis.rbac.raw_api.group_api.delete_role_from_group(group.uuid, roles_string)


@pytest.fixture(scope="module")
def rbac_setup_granular_hosts_permissions_for_sa(
    host_inventory: ApplicationHostInventory,
    rbac_setup_resources: RBACResources,
    rbac_clean_service_account_regular_group,
):
    inv_group = rbac_setup_resources.groups[0]
    rbac_group = host_inventory.apis.rbac.get_group_by_name(RBAC_GROUP_SERVICE_ACCOUNT_REGULAR)

    if host_inventory.unleash.is_rbac_workspaces_enabled:
        role = host_inventory.apis.rbac.create_role_v2(RBACInventoryPermission.HOSTS_ALL)
        host_inventory.apis.rbac.create_role_bindings([role.id], rbac_group.uuid, [inv_group.id])
    else:
        role = host_inventory.apis.rbac.create_role_v1(
            RBACInventoryPermission.HOSTS_ALL, hbi_groups=[inv_group]
        )
        host_inventory.apis.rbac.add_roles_to_a_group([role], rbac_group.uuid)

    wait_for_kessel_sync(host_inventory)

    yield

    host_inventory.apis.rbac.delete_role(get_role_id(role))


@pytest.fixture(params=[RBACRoles.RHEL_ADMIN, RBACRoles.RHEL_OPERATOR, RBACRoles.RHEL_VIEWER])
def rbac_setup_user_with_rhel_role(
    hbi_non_org_admin_user_username: str,
    host_inventory: ApplicationHostInventory,
    request: FixtureRequest,
) -> Generator[str]:
    host_inventory.apis.rbac.reset_user_groups(hbi_non_org_admin_user_username)

    group = host_inventory.apis.rbac.create_group(request.param)
    host_inventory.apis.rbac.add_user_to_a_group(hbi_non_org_admin_user_username, group.uuid)

    role = host_inventory.apis.rbac.get_role_by_name(request.param.value)
    if host_inventory.unleash.is_rbac_workspaces_enabled:
        workspace_id = host_inventory.apis.workspaces.default_workspace.id
        host_inventory.apis.rbac.create_role_bindings(
            [get_role_id(role)], group.uuid, [workspace_id]
        )
    else:
        host_inventory.apis.rbac.add_roles_to_a_group([role], group.uuid)

    wait_for_kessel_sync(host_inventory)

    yield request.param.value

    host_inventory.apis.rbac.delete_group(group.uuid)

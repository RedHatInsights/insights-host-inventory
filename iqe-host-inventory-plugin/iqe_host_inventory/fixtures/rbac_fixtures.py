from __future__ import annotations

import logging
from collections.abc import Generator
from time import sleep
from typing import NamedTuple

import pytest
from iqe.base.application import Application
from iqe.base.application.implementations.rest import ViaREST
from iqe_rbac.entities.group import Group

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.groups_api import GROUP_OR_ID
from iqe_host_inventory.modeling.groups_api import GroupData
from iqe_host_inventory.utils.datagen_utils import TagDict
from iqe_host_inventory.utils.datagen_utils import gen_tag
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory.utils.rbac_utils import RBACInventoryPermission
from iqe_host_inventory.utils.rbac_utils import RBACRoles
from iqe_host_inventory.utils.rbac_utils import update_group_with_roles
from iqe_host_inventory_api import GroupOutWithHostCount
from iqe_host_inventory_api import HostOut

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

        to_delete.append((group.uuid, [role.uuid for role in roles]))

        host_inventory.apis.rbac.check_inventory_user_permission(
            hbi_non_org_admin_user_username,
            permissions,
            hbi_groups=hbi_groups,
        )

    yield _rbac_inventory_user_setup

    for rbac_setup in to_delete:
        host_inventory.apis.rbac.delete_group(rbac_setup[0])
        for uuid in rbac_setup[1]:
            host_inventory.apis.rbac.delete_role(uuid)


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
    ) -> None:
        group, roles = host_inventory.apis.rbac.setup_rbac_user(
            hbi_non_org_admin_user_username, permissions, hbi_groups=hbi_groups
        )
        to_delete.append((group.uuid, [role.uuid for role in roles]))

        host_inventory.apis.rbac.check_inventory_user_permission(
            hbi_non_org_admin_user_username,
            permissions,
            hbi_groups=hbi_groups,
        )

    yield _rbac_inventory_user_setup

    for rbac_setup in to_delete:
        host_inventory.apis.rbac.delete_group(rbac_setup[0])
        for uuid in rbac_setup[1]:
            host_inventory.apis.rbac.delete_role(uuid)


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
    host_inventory.apis.rbac.add_roles_to_a_group([role], group.uuid)

    yield host_inventory_non_org_admin

    host_inventory.apis.rbac.delete_group(group.uuid)


@pytest.fixture(scope="function")
def rbac_inventory_hosts_read_user_setup(hbi_non_org_admin_user_rbac_setup):
    hbi_non_org_admin_user_rbac_setup(permissions=[RBACInventoryPermission.HOSTS_READ])


@pytest.fixture(scope="function")
def rbac_inventory_groups_read_user_setup(hbi_non_org_admin_user_rbac_setup):
    hbi_non_org_admin_user_rbac_setup(permissions=[RBACInventoryPermission.GROUPS_READ])


@pytest.fixture(scope="function")
def rbac_inventory_all_read_user_setup(hbi_non_org_admin_user_rbac_setup):
    hbi_non_org_admin_user_rbac_setup(permissions=[RBACInventoryPermission.ALL_READ])


@pytest.fixture(scope="function")
def rbac_inventory_hosts_write_user_setup(hbi_non_org_admin_user_rbac_setup):
    hbi_non_org_admin_user_rbac_setup(permissions=[RBACInventoryPermission.HOSTS_WRITE])


@pytest.fixture(scope="function")
def rbac_inventory_groups_write_user_setup(hbi_non_org_admin_user_rbac_setup):
    hbi_non_org_admin_user_rbac_setup(permissions=[RBACInventoryPermission.GROUPS_WRITE])


@pytest.fixture(scope="function")
def rbac_inventory_hosts_all_user_setup(hbi_non_org_admin_user_rbac_setup):
    hbi_non_org_admin_user_rbac_setup(permissions=[RBACInventoryPermission.HOSTS_ALL])


@pytest.fixture(scope="function")
def rbac_inventory_groups_all_user_setup(hbi_non_org_admin_user_rbac_setup):
    hbi_non_org_admin_user_rbac_setup(permissions=[RBACInventoryPermission.GROUPS_ALL])


@pytest.fixture(scope="function")
def rbac_inventory_admin_user_setup(hbi_non_org_admin_user_rbac_setup):
    hbi_non_org_admin_user_rbac_setup(permissions=[RBACInventoryPermission.ADMIN])


@pytest.fixture(scope="function")
def rbac_inventory_user_without_permissions_setup(
    host_inventory: ApplicationHostInventory, hbi_non_org_admin_user_username: str
):
    host_inventory.apis.rbac.reset_user_groups(hbi_non_org_admin_user_username)


@pytest.fixture(scope="function")
def rbac_staleness_read_hosts_read_user_setup(hbi_non_org_admin_user_rbac_setup):
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.STALENESS_READ, RBACInventoryPermission.HOSTS_READ]
    )


@pytest.fixture(scope="function")
def rbac_staleness_read_hosts_all_user_setup(hbi_non_org_admin_user_rbac_setup):
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.STALENESS_READ, RBACInventoryPermission.HOSTS_ALL]
    )


@pytest.fixture(scope="function")
def rbac_staleness_all_hosts_read_user_setup(hbi_non_org_admin_user_rbac_setup):
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.STALENESS_ALL, RBACInventoryPermission.HOSTS_READ]
    )


@pytest.fixture(scope="function")
def rbac_staleness_all_hosts_all_user_setup(hbi_non_org_admin_user_rbac_setup):
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.STALENESS_ALL, RBACInventoryPermission.HOSTS_ALL]
    )


@pytest.fixture(scope="function")
def rbac_staleness_write_user_setup(hbi_non_org_admin_user_rbac_setup):
    hbi_non_org_admin_user_rbac_setup(permissions=[RBACInventoryPermission.STALENESS_WRITE])


@pytest.fixture(scope="function")
def rbac_staleness_read_hosts_write_user_setup(hbi_non_org_admin_user_rbac_setup):
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.STALENESS_READ, RBACInventoryPermission.HOSTS_WRITE]
    )


@pytest.fixture(scope="function")
def rbac_staleness_write_hosts_read_user_setup(hbi_non_org_admin_user_rbac_setup):
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.STALENESS_WRITE, RBACInventoryPermission.HOSTS_READ]
    )


@pytest.fixture(scope="function")
def rbac_staleness_read_user_setup(hbi_non_org_admin_user_rbac_setup):
    hbi_non_org_admin_user_rbac_setup(permissions=[RBACInventoryPermission.STALENESS_READ])


@pytest.fixture(scope="function")
def rbac_staleness_all_user_setup(hbi_non_org_admin_user_rbac_setup):
    hbi_non_org_admin_user_rbac_setup(permissions=[RBACInventoryPermission.STALENESS_ALL])


@pytest.fixture(scope="function")
def rbac_staleness_write_hosts_write_user_setup(hbi_non_org_admin_user_rbac_setup):
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.STALENESS_WRITE, RBACInventoryPermission.HOSTS_WRITE]
    )


@pytest.fixture(scope="function")
def rbac_staleness_write_hosts_all_user_setup(hbi_non_org_admin_user_rbac_setup):
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.STALENESS_WRITE, RBACInventoryPermission.HOSTS_ALL]
    )


@pytest.fixture(scope="function")
def rbac_staleness_all_hosts_write_user_setup(hbi_non_org_admin_user_rbac_setup):
    hbi_non_org_admin_user_rbac_setup(
        permissions=[RBACInventoryPermission.STALENESS_ALL, RBACInventoryPermission.HOSTS_WRITE]
    )


@pytest.fixture(scope="class")
def rbac_inventory_hosts_read_user_setup_class(hbi_non_org_admin_user_rbac_setup_class):
    hbi_non_org_admin_user_rbac_setup_class(permissions=[RBACInventoryPermission.HOSTS_READ])


@pytest.fixture(scope="class")
def rbac_inventory_groups_read_user_setup_class(hbi_non_org_admin_user_rbac_setup_class):
    hbi_non_org_admin_user_rbac_setup_class(permissions=[RBACInventoryPermission.GROUPS_READ])


@pytest.fixture(scope="class")
def rbac_inventory_all_read_user_setup_class(hbi_non_org_admin_user_rbac_setup_class):
    hbi_non_org_admin_user_rbac_setup_class(permissions=[RBACInventoryPermission.ALL_READ])


@pytest.fixture(scope="class")
def rbac_inventory_hosts_write_user_setup_class(hbi_non_org_admin_user_rbac_setup_class):
    hbi_non_org_admin_user_rbac_setup_class(permissions=[RBACInventoryPermission.HOSTS_WRITE])


@pytest.fixture(scope="class")
def rbac_inventory_groups_write_user_setup_class(hbi_non_org_admin_user_rbac_setup_class):
    hbi_non_org_admin_user_rbac_setup_class(permissions=[RBACInventoryPermission.GROUPS_WRITE])


@pytest.fixture(scope="class")
def rbac_inventory_hosts_all_user_setup_class(hbi_non_org_admin_user_rbac_setup_class):
    hbi_non_org_admin_user_rbac_setup_class(permissions=[RBACInventoryPermission.HOSTS_ALL])


@pytest.fixture(scope="class")
def rbac_inventory_groups_all_user_setup_class(hbi_non_org_admin_user_rbac_setup_class):
    hbi_non_org_admin_user_rbac_setup_class(permissions=[RBACInventoryPermission.GROUPS_ALL])


@pytest.fixture(scope="class")
def rbac_inventory_admin_user_setup_class(hbi_non_org_admin_user_rbac_setup_class):
    hbi_non_org_admin_user_rbac_setup_class(permissions=[RBACInventoryPermission.ADMIN])


@pytest.fixture(scope="class")
def rbac_inventory_hosts_read_granular_user_setup_class(
    rbac_setup_resources_for_granular_rbac: RBacResources, hbi_non_org_admin_user_rbac_setup_class
) -> RBacResources:
    hbi_non_org_admin_user_rbac_setup_class(
        permissions=[RBACInventoryPermission.HOSTS_READ],
        hbi_groups=rbac_setup_resources_for_granular_rbac[1][:2],
    )
    return rbac_setup_resources_for_granular_rbac


@pytest.fixture(scope="class")
def rbac_inventory_groups_read_granular_user_setup_class(
    rbac_setup_resources_for_granular_rbac: RBacResources, hbi_non_org_admin_user_rbac_setup_class
) -> RBacResources:
    hbi_non_org_admin_user_rbac_setup_class(
        permissions=[RBACInventoryPermission.GROUPS_READ],
        hbi_groups=rbac_setup_resources_for_granular_rbac[1][:2],
    )
    return rbac_setup_resources_for_granular_rbac


@pytest.fixture(scope="class")
def rbac_inventory_all_read_granular_user_setup_class(
    rbac_setup_resources_for_granular_rbac: RBacResources, hbi_non_org_admin_user_rbac_setup_class
) -> RBacResources:
    hbi_non_org_admin_user_rbac_setup_class(
        permissions=[RBACInventoryPermission.ALL_READ],
        hbi_groups=rbac_setup_resources_for_granular_rbac[1][:2],
    )
    return rbac_setup_resources_for_granular_rbac


@pytest.fixture(scope="class")
def rbac_inventory_hosts_write_granular_user_setup_class(
    rbac_setup_resources_for_granular_rbac: RBacResources, hbi_non_org_admin_user_rbac_setup_class
) -> RBacResources:
    hbi_non_org_admin_user_rbac_setup_class(
        permissions=[RBACInventoryPermission.HOSTS_WRITE],
        hbi_groups=rbac_setup_resources_for_granular_rbac[1][:2],
    )
    return rbac_setup_resources_for_granular_rbac


@pytest.fixture(scope="class")
def rbac_inventory_groups_write_granular_user_setup_class(
    rbac_setup_resources_for_granular_rbac: RBacResources, hbi_non_org_admin_user_rbac_setup_class
) -> RBacResources:
    hbi_non_org_admin_user_rbac_setup_class(
        permissions=[RBACInventoryPermission.GROUPS_WRITE],
        hbi_groups=rbac_setup_resources_for_granular_rbac[1][:2],
    )
    return rbac_setup_resources_for_granular_rbac


@pytest.fixture(scope="class")
def rbac_inventory_hosts_all_granular_user_setup_class(
    rbac_setup_resources_for_granular_rbac: RBacResources, hbi_non_org_admin_user_rbac_setup_class
) -> RBacResources:
    hbi_non_org_admin_user_rbac_setup_class(
        permissions=[RBACInventoryPermission.HOSTS_ALL],
        hbi_groups=rbac_setup_resources_for_granular_rbac[1][:2],
    )
    return rbac_setup_resources_for_granular_rbac


@pytest.fixture(scope="class")
def rbac_inventory_groups_all_granular_user_setup_class(
    rbac_setup_resources_for_granular_rbac: RBacResources, hbi_non_org_admin_user_rbac_setup_class
) -> RBacResources:
    hbi_non_org_admin_user_rbac_setup_class(
        permissions=[RBACInventoryPermission.GROUPS_ALL],
        hbi_groups=rbac_setup_resources_for_granular_rbac[1][:2],
    )
    return rbac_setup_resources_for_granular_rbac


@pytest.fixture(scope="class")
def rbac_inventory_admin_granular_user_setup_class(
    rbac_setup_resources_for_granular_rbac: RBacResources, hbi_non_org_admin_user_rbac_setup_class
) -> RBacResources:
    hbi_non_org_admin_user_rbac_setup_class(
        permissions=[RBACInventoryPermission.ADMIN],
        hbi_groups=rbac_setup_resources_for_granular_rbac[1][:2],
    )
    return rbac_setup_resources_for_granular_rbac


@pytest.fixture(scope="class")
def rbac_inventory_user_without_permissions_setup_class(
    host_inventory: ApplicationHostInventory, hbi_non_org_admin_user_username: str
):
    host_inventory.apis.rbac.reset_user_groups(hbi_non_org_admin_user_username)


@pytest.fixture(scope="class")
def rbac_staleness_read_hosts_read_user_setup_class(
    hbi_non_org_admin_user_rbac_setup_class,
):
    hbi_non_org_admin_user_rbac_setup_class(
        permissions=[RBACInventoryPermission.STALENESS_READ, RBACInventoryPermission.HOSTS_READ]
    )


@pytest.fixture(scope="class")
def rbac_staleness_read_hosts_all_user_setup_class(
    hbi_non_org_admin_user_rbac_setup_class,
):
    hbi_non_org_admin_user_rbac_setup_class(
        permissions=[RBACInventoryPermission.STALENESS_READ, RBACInventoryPermission.HOSTS_ALL]
    )


@pytest.fixture(scope="class")
def rbac_staleness_all_hosts_read_user_setup_class(
    hbi_non_org_admin_user_rbac_setup_class,
):
    hbi_non_org_admin_user_rbac_setup_class(
        permissions=[RBACInventoryPermission.STALENESS_ALL, RBACInventoryPermission.HOSTS_READ]
    )


@pytest.fixture(scope="class")
def rbac_staleness_all_hosts_all_user_setup_class(
    hbi_non_org_admin_user_rbac_setup_class,
):
    hbi_non_org_admin_user_rbac_setup_class(
        permissions=[RBACInventoryPermission.STALENESS_ALL, RBACInventoryPermission.HOSTS_ALL]
    )


@pytest.fixture(scope="class")
def rbac_staleness_write_user_setup_class(hbi_non_org_admin_user_rbac_setup_class):
    hbi_non_org_admin_user_rbac_setup_class(permissions=[RBACInventoryPermission.STALENESS_WRITE])


@pytest.fixture(scope="class")
def rbac_staleness_read_hosts_write_user_setup_class(
    hbi_non_org_admin_user_rbac_setup_class,
):
    hbi_non_org_admin_user_rbac_setup_class(
        permissions=[RBACInventoryPermission.STALENESS_READ, RBACInventoryPermission.HOSTS_WRITE]
    )


@pytest.fixture(scope="class")
def rbac_staleness_write_hosts_read_user_setup_class(
    hbi_non_org_admin_user_rbac_setup_class,
):
    hbi_non_org_admin_user_rbac_setup_class(
        permissions=[RBACInventoryPermission.STALENESS_WRITE, RBACInventoryPermission.HOSTS_READ]
    )


@pytest.fixture(scope="class")
def rbac_staleness_read_user_setup_class(hbi_non_org_admin_user_rbac_setup_class):
    hbi_non_org_admin_user_rbac_setup_class(permissions=[RBACInventoryPermission.STALENESS_READ])


@pytest.fixture(scope="class")
def rbac_staleness_all_user_setup_class(hbi_non_org_admin_user_rbac_setup_class):
    hbi_non_org_admin_user_rbac_setup_class(permissions=[RBACInventoryPermission.STALENESS_ALL])


@pytest.fixture(scope="class")
def rbac_staleness_write_hosts_write_user_setup_class(
    hbi_non_org_admin_user_rbac_setup_class,
):
    hbi_non_org_admin_user_rbac_setup_class(
        permissions=[RBACInventoryPermission.STALENESS_WRITE, RBACInventoryPermission.HOSTS_WRITE]
    )


@pytest.fixture(scope="class")
def rbac_staleness_write_hosts_all_user_setup_class(
    hbi_non_org_admin_user_rbac_setup_class,
):
    hbi_non_org_admin_user_rbac_setup_class(
        permissions=[RBACInventoryPermission.STALENESS_WRITE, RBACInventoryPermission.HOSTS_ALL]
    )


@pytest.fixture(scope="class")
def rbac_staleness_all_hosts_write_user_setup_class(
    hbi_non_org_admin_user_rbac_setup_class,
):
    hbi_non_org_admin_user_rbac_setup_class(
        permissions=[RBACInventoryPermission.STALENESS_ALL, RBACInventoryPermission.HOSTS_WRITE]
    )


@pytest.fixture(scope="module")
def rbac_setup_resources(
    host_inventory: ApplicationHostInventory,
) -> tuple[list[HostOut], list[GroupOutWithHostCount], list[list[TagDict]]]:
    """WARNING: This will delete all existing hosts and groups and create new ones
    Returns: (
        [assigned host, not assigned host],
        [group with host, empty group],
        [tags of host1, tags of host2]
    )"""
    host_inventory.apis.hosts.confirm_delete_all()
    host_inventory.apis.groups.delete_all_groups()

    tags1 = [gen_tag()]
    host1 = host_inventory.upload.create_host(tags=tags1, cleanup_scope="module")
    tags2 = [gen_tag(), gen_tag(), gen_tag()]
    host2 = host_inventory.upload.create_host(tags=tags2, cleanup_scope="module")
    group_name = generate_display_name()
    group1 = host_inventory.apis.groups.create_group(
        group_name, hosts=host1, cleanup_scope="module"
    )
    group_name = generate_display_name()
    group2 = host_inventory.apis.groups.create_group(group_name, cleanup_scope="module")

    return [host1, host2], [group1, group2], [tags1, tags2]


@pytest.fixture(scope="class")
def rbac_cert_auth_setup_resources(
    host_inventory: ApplicationHostInventory,
    host_inventory_non_org_admin_cert_auth: ApplicationHostInventory,
) -> tuple[list[HostOut], list[GroupOutWithHostCount], list[list[TagDict]]]:
    """WARNING: This will delete all existing hosts and groups and create new ones
    Returns: (
        [assigned host, not assigned host],
        [group with host, empty group],
        [tags of host1, tags of host2]
    )"""
    host_inventory.apis.hosts.confirm_delete_all()
    host_inventory.apis.groups.delete_all_groups()

    tags1 = [gen_tag()]
    host1 = host_inventory_non_org_admin_cert_auth.upload.create_host(
        tags=tags1, cleanup_scope="class"
    )
    tags2 = [gen_tag(), gen_tag(), gen_tag()]
    host2 = host_inventory_non_org_admin_cert_auth.upload.create_host(
        tags=tags2, cleanup_scope="class"
    )

    groups_data = [GroupData(hosts=[host1]), GroupData(hosts=[])]
    groups = host_inventory.apis.groups.create_groups(groups_data, cleanup_scope="class")

    return [host1, host2], groups, [tags1, tags2]


class RBacResources(NamedTuple):
    host_groups: list[list[HostOut]]
    groups: list[GroupOutWithHostCount]


@pytest.fixture(scope="module")
def rbac_setup_resources_for_granular_rbac(
    host_inventory: ApplicationHostInventory,
) -> RBacResources:
    """WARNING: This will delete all existing hosts and groups and create new ones
    Prepares hosts and groups for granular RBAC tests.
    Group1 and group2 should be in attributeFilter, group3 shouldn't be.
    First 3 hosts should be accessible. Host from group3 and host without group shouldn't be.

    Returns: (
        [hosts in group1 (1), hosts in group2 (2), hosts in group3 (1), hosts without group (1)],
        [group1 (with 1 host), group2 (with 2 hosts), group3 (with 1 host)]
    )"""
    host_inventory.apis.hosts.confirm_delete_all()
    host_inventory.apis.groups.delete_all_groups()

    hosts: list[HostOut] = host_inventory.upload.create_hosts(5, cleanup_scope="module")
    groups_data = [
        GroupData(hosts=[hosts[0]]),
        GroupData(hosts=hosts[1:3]),
        GroupData(hosts=[hosts[3]]),
    ]
    groups = host_inventory.apis.groups.create_groups(groups_data, cleanup_scope="module")

    return RBacResources(
        host_groups=[hosts[:1], hosts[1:3], [hosts[3]], [hosts[4]]], groups=groups
    )


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
    rbac_setup_resources_for_granular_rbac: RBacResources,
    rbac_clean_service_account_regular_group,
):
    inv_group = rbac_setup_resources_for_granular_rbac.groups[0]
    rbac_group = host_inventory.apis.rbac.get_group_by_name(RBAC_GROUP_SERVICE_ACCOUNT_REGULAR)
    role = host_inventory.apis.rbac.create_role(
        RBACInventoryPermission.HOSTS_ALL, hbi_groups=[inv_group]
    )
    host_inventory.apis.rbac.add_roles_to_a_group([role], rbac_group.uuid)

    yield

    host_inventory.apis.rbac.delete_role(role.uuid)


@pytest.fixture
def rbac_setup_group_with_member(
    application: Application, hbi_non_org_admin_user_username: str
) -> Generator[tuple[Group, Application]]:
    with application.context.use(ViaREST):
        group = application.rbac.collections.groups.create(
            name=generate_display_name(),
            members=[
                application.rbac.collections.users.instantiate(hbi_non_org_admin_user_username)
            ],
        )

    yield group, application

    with application.context.use(ViaREST):
        group.delete_if_exists()


def wait_for_kessel_sync(
    is_kessel_phase_1_enabled: bool,
    wait_seconds: int = 21,
) -> None:
    """
    Wait for RBAC -> Kessel synchronization if the Kessel Phase 1 feature flag is enabled.
    """
    if is_kessel_phase_1_enabled:
        logger.info(f"Waiting {wait_seconds} seconds for RBAC -> Kessel sync...")
        sleep(wait_seconds)


@pytest.fixture
def rbac_setup_user_with_rhel_admin_role(
    rbac_setup_group_with_member, is_kessel_phase_1_enabled: bool
) -> str:
    group, app = rbac_setup_group_with_member
    update_group_with_roles(app, group, [RBACRoles.RHEL_ADMIN])

    wait_for_kessel_sync(is_kessel_phase_1_enabled)

    return RBACRoles.RHEL_ADMIN


@pytest.fixture
def rbac_setup_user_with_rhel_operator_role(
    rbac_setup_group_with_member, is_kessel_phase_1_enabled: bool
) -> str:
    group, app = rbac_setup_group_with_member
    update_group_with_roles(app, group, [RBACRoles.RHEL_OPERATOR])

    wait_for_kessel_sync(is_kessel_phase_1_enabled)

    return RBACRoles.RHEL_OPERATOR


@pytest.fixture
def rbac_setup_user_with_rhel_viewer_role(
    rbac_setup_group_with_member, is_kessel_phase_1_enabled: bool
) -> str:
    group, app = rbac_setup_group_with_member
    update_group_with_roles(app, group, [RBACRoles.RHEL_VIEWER])

    wait_for_kessel_sync(is_kessel_phase_1_enabled)

    return RBACRoles.RHEL_VIEWER

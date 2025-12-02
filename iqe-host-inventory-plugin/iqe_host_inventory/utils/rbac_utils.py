from __future__ import annotations

from enum import Enum

from iqe.base.application import Application
from iqe.base.application.implementations.rest import ViaREST
from iqe_rbac.entities.group import Group


class RBACInventoryPermission(Enum):
    HOSTS_READ = "inventory:hosts:read"
    HOSTS_WRITE = "inventory:hosts:write"
    HOSTS_ALL = "inventory:hosts:*"
    GROUPS_READ = "inventory:groups:read"
    GROUPS_WRITE = "inventory:groups:write"
    GROUPS_ALL = "inventory:groups:*"
    ALL_READ = "inventory:*:read"
    # ALL_WRITE = "inventory:*:write"  # This doesn't exist: https://github.com/RedHatInsights/rbac-config/blob/master/configs/stage/permissions/inventory.json  # noqa
    ADMIN = "inventory:*:*"
    RBAC_ADMIN = "rbac:*:*"
    STALENESS_READ = "staleness:staleness:read"
    STALENESS_WRITE = "staleness:staleness:write"
    STALENESS_ALL = "staleness:staleness:*"


class RBACRoles:
    HOSTS_VIEWER = "Inventory Hosts viewer"
    HOSTS_ADMIN = "Inventory Hosts administrator"
    GROUPS_VIEWER = "Inventory Groups viewer"
    GROUPS_ADMIN = "Inventory Groups administrator"
    RHEL_ADMIN = "RHEL admin"
    RHEL_OPERATOR = "RHEL operator"
    RHEL_VIEWER = "RHEL viewer"
    STALENESS_VIEWER = "Organization Staleness and Deletion Viewer"
    STALENESS_ADMIN = "Organization Staleness and Deletion Administrator"
    USER_ACCESS = "User Access administrator"


def update_group_with_roles(app: Application, group: Group, roles: list[str]) -> None:
    """Help function to update RBAC group with roles (which assign permissions)"""
    with app.context.use(ViaREST):
        group.update(
            roles=[app.rbac.collections.roles.instantiate(role) for role in roles],
        )

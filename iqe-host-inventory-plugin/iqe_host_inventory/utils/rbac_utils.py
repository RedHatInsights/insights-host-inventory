from __future__ import annotations

import logging
from enum import Enum
from time import sleep

from iqe_rbac_api import RoleWithAccess
from iqe_rbac_v2_api import Permission as RBACV2Permission
from iqe_rbac_v2_api import Role as RBACV2Role

from iqe_host_inventory import ApplicationHostInventory

logger = logging.getLogger(__name__)


class RBACInventoryPermission(Enum):
    HOSTS_READ = "inventory:hosts:read"
    HOSTS_WRITE = "inventory:hosts:write"
    HOSTS_ALL = "inventory:hosts:*"
    GROUPS_READ = "inventory:groups:read"
    GROUPS_WRITE = "inventory:groups:write"
    GROUPS_ALL = "inventory:groups:*"
    ALL_READ = "inventory:*:read"
    # ALL_WRITE = "inventory:*:write"  # This doesn't exist: https://github.com/RedHatInsights/rbac-config/blob/master/configs/stage/permissions/inventory.json
    ADMIN = "inventory:*:*"
    RBAC_ADMIN = "rbac:*:*"
    STALENESS_READ = "staleness:staleness:read"
    STALENESS_WRITE = "staleness:staleness:write"
    STALENESS_ALL = "staleness:staleness:*"


class RBACRoles(Enum):
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


def get_role_id(role: RoleWithAccess | RBACV2Role) -> str:
    """Get role ID from either V1 (RoleWithAccess.uuid) or V2 (Role.id) role object."""
    return getattr(role, "uuid", None) or role.id


def permission_to_v2(permission: RBACInventoryPermission) -> RBACV2Permission:
    """Convert an RBACInventoryPermission enum to a V2 Permission model."""
    app, resource_type, operation = permission.value.split(":")
    return RBACV2Permission(application=app, resource_type=resource_type, operation=operation)


def wait_for_kessel_sync(host_inventory: ApplicationHostInventory) -> None:
    """
    Wait for RBAC -> Kessel synchronization if the Kessel Phase 1 feature flag is enabled.
    """
    wait_seconds = 3 if host_inventory.application.config.current_env == "clowder_smoke" else 21
    if host_inventory.unleash.is_kessel_phase_1_enabled():
        logger.info(f"Waiting {wait_seconds} seconds for RBAC -> Kessel sync...")
        sleep(wait_seconds)

from enum import Enum
from typing import Any


class RbacPermission(Enum):
    READ = "read"
    WRITE = "write"
    ADMIN = "*"


class RbacResourceType(Enum):
    HOSTS = "hosts"
    GROUPS = "groups"
    STALENESS = "staleness"
    ALL = "*"


class KesselResourceType:
    namespace: str
    name: str
    v1_type: RbacResourceType
    v1_app: str

    def get_resource_id(self, kwargs: dict[str, Any], id_param: str) -> list[str]:
        if id_param == "":
            return []

        value = kwargs.get(id_param)

        if isinstance(value, list):
            return list(value)

        return [str(value)]

    def __init__(self, namespace: str, name: str, v1_type: RbacResourceType, v1_app: str) -> None:
        self.namespace = namespace
        self.name = name
        self.v1_type = v1_type
        self.v1_app = v1_app


class KesselPermission:
    resource_type: KesselResourceType
    workspace_permission: str
    resource_permission: str
    v1_permission: RbacPermission

    def __init__(
        self,
        resourceType: KesselResourceType,
        workspacePermission: str,
        resourcePermission: str,
        v1Permission: RbacPermission,
    ) -> None:
        self.resource_type = resourceType
        self.workspace_permission = workspacePermission
        self.resource_permission = resourcePermission
        self.v1_permission = v1Permission


class HostKesselResourceType(KesselResourceType):
    def __init__(self) -> None:
        super().__init__("hbi", "host", RbacResourceType.HOSTS, "inventory")
        self.view = KesselPermission(self, "inventory_host_view", "view", RbacPermission.READ)
        self.update = KesselPermission(self, "inventory_host_update", "update", RbacPermission.WRITE)
        self.move = KesselPermission(self, "inventory_host_move", "move", RbacPermission.WRITE)
        self.delete = KesselPermission(self, "inventory_host_delete", "delete", RbacPermission.WRITE)


class WorkspaceKesselResourceType(KesselResourceType):
    def __init__(self) -> None:
        super().__init__("rbac", "workspace", RbacResourceType.GROUPS, "inventory")
        self.move_host = KesselPermission(self, "inventory_host_move", "inventory_host_move", RbacPermission.WRITE)


class GroupKesselResourceType(KesselResourceType):
    def __init__(self) -> None:
        super().__init__("hbi", "group", RbacResourceType.GROUPS, "inventory")
        self.view = KesselPermission(self, "inventory_groups_view", "view", RbacPermission.READ)
        self.write = KesselPermission(self, "inventory_groups_update", "edit", RbacPermission.WRITE)
        self.delete = KesselPermission(self, "inventory_groups_update", "delete", RbacPermission.WRITE)
        self.create = KesselPermission(self, "inventory_groups_update", "create", RbacPermission.WRITE)


class StalenessKesselResourceType(KesselResourceType):
    def get_resource_id(self, kwargs: dict[str, Any], id_param: str) -> list[str]:  # noqa: ARG002, overrides get_resource_id from KesselResourceType
        from lib.middleware import get_rbac_default_workspace

        workspace_id = get_rbac_default_workspace()
        if workspace_id:
            return [str(workspace_id)]
        else:
            return []

    def __init__(self) -> None:
        super().__init__("rbac", "workspace", RbacResourceType.STALENESS, "staleness")
        self.view = KesselPermission(self, "staleness_staleness_view", "staleness_staleness_view", RbacPermission.READ)
        self.update = KesselPermission(
            self, "staleness_staleness_update", "staleness_staleness_update", RbacPermission.WRITE
        )


class AllKesselResourceType(KesselResourceType):
    def __init__(self) -> None:
        super().__init__("hbi", "all", RbacResourceType.ALL, "inventory")
        self.admin = KesselPermission(self, "inventory_admin", "admin", RbacPermission.ADMIN)


# Add more resource types as subclasses of KesselResourceType


class KesselResourceTypes:
    HOST = HostKesselResourceType()
    WORKSPACE = WorkspaceKesselResourceType()
    GROUP = GroupKesselResourceType()
    STALENESS = StalenessKesselResourceType()
    ALL = AllKesselResourceType()
    # Expose resource type specific subclasses here

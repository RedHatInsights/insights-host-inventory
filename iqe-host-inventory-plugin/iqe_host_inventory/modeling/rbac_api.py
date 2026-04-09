# mypy: disallow-untyped-defs

from __future__ import annotations

import logging
from collections.abc import Sequence
from copy import deepcopy
from functools import cached_property

import attr
from iqe.base.modeling import BaseEntity
from iqe_rbac import ApplicationRBAC
from iqe_rbac_api import ApiException as RBACApiException
from iqe_rbac_api import GroupOut as RBACGroupOut
from iqe_rbac_api import GroupWithPrincipalsAndRoles
from iqe_rbac_api import RoleWithAccess
from iqe_rbac_v2_api import ApiException as RBACV2ApiException
from iqe_rbac_v2_api import Role as RBACV2Role
from iqe_rbac_v2_api import RoleBindingsBatchCreateRoleBindingsRequest
from iqe_rbac_v2_api import RoleBindingsBatchCreateRoleBindingsResponse
from iqe_rbac_v2_api import RoleBindingsCreateRoleBindingsRequest
from iqe_rbac_v2_api import RoleBindingsCreateRoleBindingsRequestResource
from iqe_rbac_v2_api import RoleBindingsCreateRoleBindingsRequestRole
from iqe_rbac_v2_api import RoleBindingsCreateRoleBindingsRequestSubject
from iqe_rbac_v2_api import RoleBindingsSubjectType
from iqe_rbac_v2_api import RolesBatchDeleteRolesRequest
from iqe_rbac_v2_api import RolesCreateOrUpdateRoleRequest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.groups_api import GROUP_OR_ID
from iqe_host_inventory.modeling.groups_api import _ids_from_groups
from iqe_host_inventory.schemas import RBACRestClient
from iqe_host_inventory.schemas import RBACRestClientV2
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.rbac_utils import RBACInventoryPermission
from iqe_host_inventory.utils.rbac_utils import permission_to_v2
from iqe_host_inventory.utils.rbac_utils import wait_for_kessel_sync

logger = logging.getLogger(__name__)


def _hbi_groups_to_ids(hbi_groups: Sequence[GROUP_OR_ID | None] | None) -> Sequence[str | None]:
    groups = deepcopy(hbi_groups)
    if groups is None:
        groups = []

    without_nulls = [x for x in groups if x is not None]

    ids = _ids_from_groups(without_nulls)

    if len(without_nulls) < len(groups):
        return [*ids, None]
    else:
        return ids


@attr.s
class RBACAPIWrapper(BaseEntity):
    @cached_property
    def _host_inventory(self) -> ApplicationHostInventory:
        return self.application.host_inventory

    @cached_property
    def _rbac(self) -> ApplicationRBAC:
        return self.application.rbac

    @cached_property
    def raw_api(self) -> RBACRestClient:
        return self._rbac.rest_client

    @cached_property
    def raw_api_v2(self) -> RBACRestClientV2:
        return self._rbac.rest_client_v2

    def create_group(
        self,
        permission: RBACInventoryPermission,
        *,
        hbi_groups: Sequence[GROUP_OR_ID | None] | None = None,
        name: str | None = None,
        description: str | None = None,
    ) -> RBACGroupOut:
        hbi_groups_ids = _hbi_groups_to_ids(hbi_groups)
        permission_v = permission.value

        name = f"iqe-hbi-group_{generate_uuid()}" if name is None else name
        description = (
            f"Inventory group for {permission_v} permission tests with groups: {hbi_groups_ids}"
            if description is None
            else description
        )

        return self.raw_api.group_api.create_group({"name": name, "description": description})

    def add_user_to_a_group(self, username: str, group_uuid: str) -> GroupWithPrincipalsAndRoles:
        return self.raw_api.group_api.add_principal_to_group(
            group_uuid, {"principals": [{"username": username}]}
        )

    def remove_user_from_group(self, username: str, group_uuid: str) -> None:
        try:
            self.raw_api.group_api.delete_principal_from_group(group_uuid, usernames=username)
        except RBACApiException as exc:
            assert exc.status == 404

    def delete_group(self, group_uuid: str) -> None:
        if self._host_inventory.unleash.is_rbac_workspaces_enabled:
            self.reset_role_bindings(group_uuid)
        try:
            self.raw_api.group_api.delete_group(group_uuid)
        except RBACApiException as exc:
            assert exc.status == 404

    def create_role_v1(
        self,
        permission: RBACInventoryPermission,
        *,
        hbi_groups: Sequence[GROUP_OR_ID | None] | None = None,
        key: str = "group.id",
        operation: str = "in",
        name: str | None = None,
        description: str | None = None,
    ) -> RoleWithAccess:
        hbi_group_ids = _hbi_groups_to_ids(hbi_groups)
        permission_v = permission.value
        application = permission_v.split(":")[0]

        name = f"iqe-hbi-role_{generate_uuid()}" if name is None else name
        description = (
            f"Inventory role for {permission_v} permission tests with groups: {hbi_group_ids}"
            if description is None
            else description
        )

        if hbi_group_ids:
            definitions = [
                {"attributeFilter": {"key": key, "value": hbi_group_ids, "operation": operation}}
            ]
        else:
            definitions = []

        permissions = [{"permission": permission_v, "resourceDefinitions": definitions}]

        return self.raw_api.role_api.create_role({
            "name": name,
            "description": description,
            "access": permissions,
            "applications": [application],
        })

    def create_role_v2(
        self,
        permission: RBACInventoryPermission,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> RBACV2Role:
        permission_v = permission.value

        name = f"iqe-hbi-role_{generate_uuid()}" if name is None else name
        description = (
            f"Inventory role for {permission_v} permission tests"
            if description is None
            else description
        )

        v2_permission = permission_to_v2(permission)
        return self.raw_api_v2.roles_api.roles_create(
            RolesCreateOrUpdateRoleRequest(
                name=name,
                description=description,
                permissions=[v2_permission],
            )
        )

    def add_roles_to_a_group(self, roles: list[RoleWithAccess], group_uuid: str) -> None:
        role_uuids = [role.uuid for role in roles]
        self.raw_api.group_api.add_role_to_group(group_uuid, {"roles": role_uuids})

    def create_role_bindings(
        self,
        role_ids: Sequence[str],
        group_uuid: str,
        workspace_ids: Sequence[str],
    ) -> RoleBindingsBatchCreateRoleBindingsResponse:
        requests = []
        for role_id in role_ids:
            for workspace_id in workspace_ids:
                requests.append(
                    RoleBindingsCreateRoleBindingsRequest(
                        resource=RoleBindingsCreateRoleBindingsRequestResource(
                            id=workspace_id, type="workspace"
                        ),
                        subject=RoleBindingsCreateRoleBindingsRequestSubject(
                            id=group_uuid, type=RoleBindingsSubjectType.GROUP
                        ),
                        role=RoleBindingsCreateRoleBindingsRequestRole(id=role_id),
                    )
                )
        return self.raw_api_v2.role_bindings_api.role_bindings_batch_create(
            RoleBindingsBatchCreateRoleBindingsRequest(requests=requests)
        )

    def delete_role_v1(self, role_uuid: str) -> None:
        try:
            self.raw_api.role_api.delete_role(role_uuid)
        except RBACApiException as exc:
            assert exc.status == 404

    def delete_role_v2(self, role_id: str) -> None:
        try:
            self.raw_api_v2.roles_api.roles_batch_delete(
                RolesBatchDeleteRolesRequest(ids=[role_id])
            )
        except RBACV2ApiException as exc:
            assert exc.status == 404

    def delete_role(self, role_id: str) -> None:
        if self._host_inventory.unleash.is_rbac_workspaces_enabled:
            self.delete_role_v2(role_id)
        else:
            self.delete_role_v1(role_id)

    def reset_role_bindings(self, group_uuid: str) -> None:
        """Remove all role bindings for a group by deleting the bound IQE-created roles.

        In RBAC V2 a group cannot be deleted while role bindings reference it.
        There is no "delete role binding" API, so the only way to remove
        bindings is to delete the roles they reference.  Only IQE-created roles
        (name prefix ``iqe-hbi-role_``) are deleted; system/pre-configured
        roles are left untouched.
        """
        response = self.raw_api_v2.role_bindings_api.role_bindings_list(
            subject_type=RoleBindingsSubjectType.GROUP,
            subject_id=group_uuid,
            limit=10000,
        )
        role_ids_to_delete = {binding.role.id for binding in response.data}
        for role_id in role_ids_to_delete:
            self.delete_role_v2(role_id)

    def reset_user_groups(
        self, username: str, group_name: str | None = "iqe-hbi", delete_groups: bool = True
    ) -> None:
        user_groups = self.raw_api.group_api.list_groups(name=group_name, username=username)

        for group in user_groups.data:
            if group.name in ("Custom default access", "Default access", "Default admin access"):
                # This is a platform_default group and principal assignments can't be modified
                continue
            if delete_groups:
                if self._host_inventory.unleash.is_rbac_workspaces_enabled:
                    self.reset_role_bindings(group.uuid)
                self.delete_group(group.uuid)
            else:
                self.remove_user_from_group(username, group.uuid)

    def setup_rbac_user(
        self,
        username: str,
        permissions: list[RBACInventoryPermission],
        *,
        hbi_groups: Sequence[GROUP_OR_ID | None] | None = None,
    ) -> tuple[RBACGroupOut, list[RoleWithAccess] | list[RBACV2Role]]:
        self.reset_user_groups(username)

        group = self.create_group(permissions[0], hbi_groups=hbi_groups)
        self.add_user_to_a_group(username, group.uuid)

        if self._host_inventory.unleash.is_rbac_workspaces_enabled:
            roles: list[RoleWithAccess] | list[RBACV2Role] = [
                self.create_role_v2(perm) for perm in permissions
            ]
            if hbi_groups:
                ungrouped_ws_id = self._host_inventory.apis.workspaces.ungrouped_workspace.id
                workspace_ids = [
                    ws_id if ws_id is not None else ungrouped_ws_id
                    for ws_id in _hbi_groups_to_ids(hbi_groups)
                ]
            else:
                workspace_ids = [self._host_inventory.apis.workspaces.root_workspace.id]
            role_ids = [role.id for role in roles]
            self.create_role_bindings(role_ids, group.uuid, workspace_ids)
        else:
            roles = [self.create_role_v1(perm, hbi_groups=hbi_groups) for perm in permissions]
            self.add_roles_to_a_group(roles, group.uuid)

        wait_for_kessel_sync(self._host_inventory)

        return group, roles

    def get_rbac_admin_role(self) -> RoleWithAccess:
        return self.raw_api.role_api.list_roles(name="User Access Administrator").data[0]

    def get_group_by_name(self, name: str) -> RBACGroupOut:
        response = self.raw_api.group_api.list_groups(name=name)
        if len(response.data) != 1:
            raise ValueError(
                f"There is less or more than 1 RBAC group with the name '{name}'", response
            )
        return response.data[0]

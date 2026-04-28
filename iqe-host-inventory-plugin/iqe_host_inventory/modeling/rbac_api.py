# mypy: disallow-untyped-defs

from __future__ import annotations

import logging
from collections.abc import Sequence
from copy import deepcopy
from functools import cached_property

import attr
from iqe.base.modeling import BaseEntity
from iqe_bindings.v7.rbac_v1 import Access
from iqe_bindings.v7.rbac_v1 import ApiException as RBACApiException
from iqe_bindings.v7.rbac_v1 import Group as RBACGroup
from iqe_bindings.v7.rbac_v1 import GroupOut as RBACGroupOut
from iqe_bindings.v7.rbac_v1 import GroupPrincipalIn
from iqe_bindings.v7.rbac_v1 import GroupPrincipalInPrincipalsInner
from iqe_bindings.v7.rbac_v1 import GroupRoleIn
from iqe_bindings.v7.rbac_v1 import GroupWithPrincipalsAndRoles
from iqe_bindings.v7.rbac_v1 import PrincipalIn
from iqe_bindings.v7.rbac_v1 import ResourceDefinition
from iqe_bindings.v7.rbac_v1 import ResourceDefinitionFilter
from iqe_bindings.v7.rbac_v1 import ResourceDefinitionFilterOperationEqual
from iqe_bindings.v7.rbac_v1 import ResourceDefinitionFilterOperationIn
from iqe_bindings.v7.rbac_v1 import RoleIn
from iqe_bindings.v7.rbac_v1 import RoleWithAccess
from iqe_bindings.v7.rbac_v2 import ApiException as RBACV2ApiException
from iqe_bindings.v7.rbac_v2 import ResourceType
from iqe_bindings.v7.rbac_v2 import Role as RBACV2Role
from iqe_bindings.v7.rbac_v2 import RoleBindingsBatchCreateRoleBindingsRequest
from iqe_bindings.v7.rbac_v2 import RoleBindingsBatchCreateRoleBindingsResponse
from iqe_bindings.v7.rbac_v2 import RoleBindingsCreateRoleBindingsRequest
from iqe_bindings.v7.rbac_v2 import RoleBindingsCreateRoleBindingsRequestResource
from iqe_bindings.v7.rbac_v2 import RoleBindingsCreateRoleBindingsRequestRole
from iqe_bindings.v7.rbac_v2 import RoleBindingsCreateRoleBindingsRequestSubject
from iqe_bindings.v7.rbac_v2 import RoleBindingsRoleBindingSubject
from iqe_bindings.v7.rbac_v2 import RoleBindingsUpdateRoleBindingsRequest
from iqe_bindings.v7.rbac_v2 import RolesBatchDeleteRolesRequest
from iqe_bindings.v7.rbac_v2 import RolesCreateOrUpdateRoleRequest

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.groups_api import GROUP_OR_ID
from iqe_host_inventory.modeling.groups_api import _ids_from_groups
from iqe_host_inventory.schemas import RBACRestClient
from iqe_host_inventory.schemas import RBACRestClientV2
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.rbac_utils import RBACInventoryPermission
from iqe_host_inventory.utils.rbac_utils import RBACRoles
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
    def raw_api(self) -> RBACRestClient:
        return self._host_inventory.v7_rbac_v1

    @cached_property
    def raw_api_v2(self) -> RBACRestClientV2:
        if not self._host_inventory.unleash.is_rbac_workspaces_enabled:
            raise RuntimeError("RBAC v2 can be used only on v2 enabled accounts")
        return self._host_inventory.v7_rbac_v2

    def create_group(
        self,
        permission: RBACInventoryPermission | RBACRoles,
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

        return self.raw_api.group_api.create_group(RBACGroup(name=name, description=description))

    def add_user_to_a_group(self, username: str, group_uuid: str) -> GroupWithPrincipalsAndRoles:
        body = GroupPrincipalIn(
            principals=[GroupPrincipalInPrincipalsInner(PrincipalIn(username=username))]
        )
        return self.raw_api.group_api.add_principal_to_group(group_uuid, body)

    def remove_user_from_group(self, username: str, group_uuid: str) -> None:
        try:
            self.raw_api.group_api.delete_principal_from_group(group_uuid, usernames=username)
        except RBACApiException as exc:
            if exc.status != 404:
                raise

    def delete_group(self, group_uuid: str) -> None:
        if self._host_inventory.unleash.is_rbac_workspaces_enabled:
            self.reset_role_bindings(group_uuid)
        try:
            self.raw_api.group_api.delete_group(group_uuid)
        except RBACApiException as exc:
            if exc.status != 404:
                raise

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
        name = f"iqe-hbi-role_{generate_uuid()}" if name is None else name
        description = (
            f"Inventory role for {permission_v} permission tests with groups: {hbi_group_ids}"
            if description is None
            else description
        )

        if hbi_group_ids:
            if operation == "in":
                attr_filter = ResourceDefinitionFilter(
                    ResourceDefinitionFilterOperationIn(
                        key=key, operation=operation, value=hbi_group_ids
                    )
                )
            else:
                attr_filter = ResourceDefinitionFilter(
                    ResourceDefinitionFilterOperationEqual(
                        key=key, operation=operation, value=hbi_group_ids
                    )
                )
            resource_defs = [ResourceDefinition(attribute_filter=attr_filter)]
        else:
            resource_defs = []

        access = [Access(permission=permission_v, resource_definitions=resource_defs)]

        application = permission_v.split(":")[0]
        role_in = RoleIn(name=name, description=description, access=access)
        role_in.additional_properties = {"applications": [application]}

        return self.raw_api.role_api.create_role(role_in)

    def create_role_v2(
        self,
        permission: RBACInventoryPermission,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> RBACV2Role:
        permission_v = permission.value

        name = f"iqe-hbi-role_{generate_uuid()}" if name is None else name
        description = description or f"Inventory role for {permission_v} permission tests"

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
        self.raw_api.group_api.add_role_to_group(group_uuid, GroupRoleIn(roles=role_uuids))

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
                            id=group_uuid, type=RoleBindingsRoleBindingSubject.GROUP
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
            if exc.status != 404:
                raise

    def delete_role_v2(self, role_id: str) -> None:
        try:
            self.raw_api_v2.roles_api.roles_batch_delete(
                RolesBatchDeleteRolesRequest(ids=[role_id])
            )
        except RBACV2ApiException as exc:
            if exc.status != 404:
                raise

    def delete_role(self, role_id: str) -> None:
        if self._host_inventory.unleash.is_rbac_workspaces_enabled:
            self.delete_role_v2(role_id)
        else:
            self.delete_role_v1(role_id)

    def reset_role_bindings(self, group_uuid: str) -> None:
        """Remove all role bindings for a group.

        In RBAC V2 a group cannot be deleted while role bindings reference it.
        Uses PUT /role-bindings/by-subject/ with an empty roles list to clear
        bindings for each (resource, subject) combination.
        """
        get_response = self.raw_api_v2.role_bindings_api.role_bindings_list(
            subject_type=RoleBindingsRoleBindingSubject.GROUP,
            subject_id=group_uuid,
            limit=10000,
        )
        # Clear bindings for each unique resource by sending an empty roles list.
        # model_construct bypasses the client-side min_length=1 validation;
        # the API itself accepts an empty list and removes all bindings.
        empty_request = RoleBindingsUpdateRoleBindingsRequest.model_construct(roles=[])
        for binding in get_response.data:
            resource = binding.resource
            put_response = (
                self.raw_api_v2.role_bindings_api.role_bindings_update_without_preload_content(
                    resource_id=resource.id,
                    resource_type=(
                        ResourceType(resource.type) if resource.type else ResourceType.WORKSPACE
                    ),
                    subject_id=group_uuid,
                    subject_type=RoleBindingsRoleBindingSubject.GROUP,
                    role_bindings_update_role_bindings_request=empty_request,
                )
            )
            # Remove these logs when https://redhat.atlassian.net/browse/RHCLOUD-46719 is fixed
            logger.info(f"{put_response.status}: {put_response.data}")

            # Enable this assert when https://redhat.atlassian.net/browse/RHCLOUD-46719 is fixed
            # assert 200 <= put_response.status <= 299, f"{put_response.status}: {put_response.data}"  # noqa: E501

    def reset_user_groups(
        self, username: str, group_name: str | None = "iqe-hbi", delete_groups: bool = True
    ) -> None:
        user_groups = self.raw_api.group_api.list_groups(name=group_name, username=username)

        for group in user_groups.data:
            if group.name in ("Custom default access", "Default access", "Default admin access"):
                # This is a platform_default group and principal assignments can't be modified
                continue
            if delete_groups:
                # Remove the try/except workaround when
                # https://redhat.atlassian.net/browse/RHCLOUD-46719 is fixed
                try:
                    self.delete_group(group.uuid)
                except RBACApiException as exc:
                    if exc.status == 400:
                        logger.info(f"Wasn't able to delete RBAC group: {exc.status}: {exc.body}")
                        logger.info("Removing user from the RBAC group")
                        self.remove_user_from_group(username, group.uuid)
                    else:
                        raise
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

    def get_role_by_name(self, name: str) -> RoleWithAccess:
        return self.raw_api.role_api.list_roles(name=name).data[0]

    def get_rbac_admin_role(self) -> RoleWithAccess:
        return self.get_role_by_name("User Access Administrator")

    def get_group_by_name(self, name: str) -> RBACGroupOut:
        response = self.raw_api.group_api.list_groups(name=name)
        if len(response.data) != 1:
            raise ValueError(
                f"There is less or more than 1 RBAC group with the name '{name}'", response
            )
        return response.data[0]

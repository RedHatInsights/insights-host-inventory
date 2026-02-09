# mypy: disallow-untyped-defs

from __future__ import annotations

import ast
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

from iqe_host_inventory.modeling.groups_api import GROUP_OR_ID
from iqe_host_inventory.modeling.groups_api import _ids_from_groups
from iqe_host_inventory.schemas import RBACRestClient
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory.utils.rbac_utils import RBACInventoryPermission
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
    def _rbac(self) -> ApplicationRBAC:
        return self.application.rbac

    @cached_property
    def raw_api(self) -> RBACRestClient:
        return self._rbac.rest_client

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

    def create_role(
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
        try:
            self.raw_api.group_api.delete_group(group_uuid)
        except RBACApiException as exc:
            assert exc.status == 404

    def add_roles_to_a_group(self, roles: list[RoleWithAccess], group_uuid: str) -> None:
        role_uuids = [role.uuid for role in roles]
        self.raw_api.group_api.add_role_to_group(group_uuid, {"roles": role_uuids})

    def delete_role(self, role_uuid: str) -> None:
        try:
            self.raw_api.role_api.delete_role(role_uuid)
        except RBACApiException as exc:
            assert exc.status == 404

    def reset_user_groups(
        self, username: str, group_name: str | None = "iqe-hbi", delete_groups: bool = True
    ) -> None:
        user_groups = self.raw_api.group_api.list_groups(name=group_name, username=username)

        for group in user_groups.data:
            if group.name in ("Custom default access", "Default access", "Default admin access"):
                # This is a platform_default group and principal assignments can't be modified
                continue
            if delete_groups:
                self.delete_group(group.uuid)
            else:
                self.remove_user_from_group(username, group.uuid)

    def check_inventory_user_permission(
        self,
        username: str,
        permissions: list[RBACInventoryPermission],
        *,
        hbi_groups: Sequence[GROUP_OR_ID | None] | None = None,
    ) -> None:
        hbi_group_ids = _hbi_groups_to_ids(hbi_groups)

        # Parse the input into a dict of app:[perms] entries so that we limit the
        # rbac calls to one per application
        perms: dict[str, list[str]] = {}
        perm_values = [perm.value for perm in permissions]
        for perm_v in perm_values:
            app = perm_v.split(":")[0]
            if app in perms:
                perms[app].append(perm_v)
            else:
                perms[app] = [perm_v]

        # Verify that the user has all expected permissions
        for app, perm_values in perms.items():
            response = self.raw_api.access_api.get_principal_access(
                application=app, username=username
            )
            assert len(response.data) == len(perm_values)
            for perm_v in perm_values:
                entry = next(
                    (entry for entry in response.data if entry.permission == perm_v), None
                )
                assert entry, f"Permission {perm_v} not found for user {username}"
                assert len(entry.resource_definitions) == (1 if hbi_group_ids else 0)
                if hbi_group_ids:
                    # Parse the string representation back to a list and compare as sets
                    # for order-independent comparison
                    actual_value = ast.literal_eval(
                        entry.resource_definitions[0].attribute_filter.value
                    )
                    expected_value = list(hbi_group_ids)
                    assert set(actual_value) == set(expected_value), (
                        f"Expected groups {expected_value}, but got {actual_value}"
                    )

    def setup_rbac_user(
        self,
        username: str,
        permissions: list[RBACInventoryPermission],
        *,
        hbi_groups: Sequence[GROUP_OR_ID | None] | None = None,
    ) -> tuple[RBACGroupOut, list[RoleWithAccess]]:
        self.reset_user_groups(username)

        group = self.create_group(permissions[0], hbi_groups=hbi_groups)
        self.add_user_to_a_group(username, group.uuid)
        roles = []
        for perm in permissions:
            roles.append(self.create_role(perm, hbi_groups=hbi_groups))

        self.add_roles_to_a_group(roles, group.uuid)

        wait_for_kessel_sync(self.application.host_inventory)

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

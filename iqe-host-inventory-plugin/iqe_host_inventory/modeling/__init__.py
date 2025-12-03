# mypy: disallow-untyped-defs

from __future__ import annotations

import logging
import os
from functools import cached_property
from typing import TYPE_CHECKING

import attr
from iqe.base.modeling import BaseEntity
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from iqe_host_inventory.utils.db_utils import Group
from iqe_host_inventory.utils.db_utils import Host
from iqe_host_inventory.utils.db_utils import HostGroupAssoc
from iqe_host_inventory.utils.db_utils import query_associations_by_group_ids
from iqe_host_inventory.utils.db_utils import query_associations_by_host_ids
from iqe_host_inventory.utils.db_utils import query_groups_by_ids
from iqe_host_inventory.utils.db_utils import query_groups_by_names
from iqe_host_inventory.utils.db_utils import query_groups_ids_all
from iqe_host_inventory.utils.db_utils import query_hosts_by_ids
from iqe_host_inventory.utils.db_utils import query_hosts_ids_all
from iqe_host_inventory.utils.kafka_utils import encode_identity
from iqe_host_inventory.utils.kafka_utils import prepare_identity_metadata

from .exports_api import ExportsAPIWrapper
from .groups_api import GROUP_OR_GROUPS
from .groups_api import GroupsAPIWrapper
from .groups_api import _ids_from_groups
from .hosts_api import HOST_OR_HOSTS
from .hosts_api import HostsAPIWrapper
from .hosts_api import _ids_from_hosts
from .rbac_api import RBACAPIWrapper
from .resource_types_api import ResourceTypesAPIWrapper
from .staleness_api import AccountStalenessAPIWrapper
from .system_profile_api import SystemProfileAPIWrapper
from .tags_api import TagsAPIWrapper
from .workspaces_api import WORKSPACE_OR_WORKSPACES
from .workspaces_api import WorkspacesAPIWrapper
from .workspaces_api import _ids_from_workspaces

if TYPE_CHECKING:
    from .. import ApplicationHostInventory

HBI_API_WRAPPER = (
    HostsAPIWrapper
    | TagsAPIWrapper
    | SystemProfileAPIWrapper
    | GroupsAPIWrapper
    | ResourceTypesAPIWrapper
    | AccountStalenessAPIWrapper
    | WorkspacesAPIWrapper
)


logger = logging.getLogger(__name__)


@attr.s(hash=False, order=False)
class HBIApis(BaseEntity):
    @cached_property
    def rest_identity(self) -> dict:
        return self.application.user.identity.to_dict()

    @cached_property
    def rest_identity_encoded(self) -> str:
        return encode_identity(self.rest_identity)

    @cached_property
    def rest_identity_metadata(self) -> dict:
        return prepare_identity_metadata(self.rest_identity)

    @cached_property
    def hosts(self) -> HostsAPIWrapper:
        return HostsAPIWrapper(self)

    @cached_property
    def tags(self) -> TagsAPIWrapper:
        return TagsAPIWrapper(self)

    @cached_property
    def system_profile(self) -> SystemProfileAPIWrapper:
        return SystemProfileAPIWrapper(self)

    @cached_property
    def groups(self) -> GroupsAPIWrapper:
        return GroupsAPIWrapper(self)

    @cached_property
    def resource_types(self) -> ResourceTypesAPIWrapper:
        return ResourceTypesAPIWrapper(self)

    @cached_property
    def rbac(self) -> RBACAPIWrapper:
        return RBACAPIWrapper(self)

    @cached_property
    def account_staleness(self) -> AccountStalenessAPIWrapper:
        return AccountStalenessAPIWrapper(self)

    @cached_property
    def exports(self) -> ExportsAPIWrapper:
        return ExportsAPIWrapper(self)

    @cached_property
    def workspaces(self) -> WorkspacesAPIWrapper:
        return WorkspacesAPIWrapper(self)


@attr.s(hash=False, order=False)
class HBIDatabase(BaseEntity):
    parent: ApplicationHostInventory

    @cached_property
    def url(self) -> URL:
        db = self.parent.config.get("db", None)
        if db is None:
            raise AttributeError("url not known")
        db_host = os.getenv("DB_HOST", db.get("hostname"))
        return URL.create(
            drivername="postgresql",
            host=db_host,
            port=db.port,
            database=db.database,
            username=db.username,
            password=db.password,
        )

    @cached_property
    def engine(self) -> Engine:
        return self.make_engine()

    @cached_property
    def read_session(self) -> Session:
        """WARNING: This session should be used only for READ operations, it doesn't do rollback"""
        session = Session(bind=self.engine)
        set_schemas = "SET SEARCH_PATH TO public,hbi"
        session.execute(set_schemas)
        return session

    def make_engine(self, echo: bool = True) -> Engine:
        return create_engine(self.url, echo=echo)

    def query_hosts_ids_all(self) -> list[str]:
        return query_hosts_ids_all(self.read_session)

    def query_hosts_by_ids(self, hosts: HOST_OR_HOSTS) -> list[Host]:
        return query_hosts_by_ids(self.read_session, _ids_from_hosts(hosts))

    def query_groups_ids_all(self) -> list[str]:
        return query_groups_ids_all(self.read_session)

    def query_groups_by_ids(self, groups: GROUP_OR_GROUPS) -> list[Group]:
        return query_groups_by_ids(self.read_session, _ids_from_groups(groups))

    def query_groups_by_names(self, group_names: list[str]) -> list[Group]:
        return query_groups_by_names(self.read_session, group_names)

    def query_associations_by_host_ids(self, hosts: HOST_OR_HOSTS) -> list[HostGroupAssoc]:
        return query_associations_by_host_ids(self.read_session, _ids_from_hosts(hosts))

    def query_associations_by_group_ids(self, groups: GROUP_OR_GROUPS) -> list[HostGroupAssoc]:
        return query_associations_by_group_ids(self.read_session, _ids_from_groups(groups))


def _check_cleanup_scope(scope: str) -> None:
    ALLOWED_SCOPES = {"function", "class", "module", "package", "session"}
    if scope not in ALLOWED_SCOPES:
        raise ValueError(f"Invalid scope: '{scope}'. Must be one of: {ALLOWED_SCOPES}")


@attr.s
class HBICleanUp(BaseEntity):
    # Key is a scope, value is a set of IDs to be cleaned within that scope
    host_ids_to_clean: dict[str, set[str]] = attr.ib(factory=dict)
    group_ids_to_clean: dict[str, set[str]] = attr.ib(factory=dict)
    export_ids_to_clean: dict[str, set[str]] = attr.ib(factory=dict)
    workspace_ids_to_clean: dict[str, set[str]] = attr.ib(factory=dict)

    def add_hosts(self, hosts: HOST_OR_HOSTS, scope: str = "function") -> None:
        _check_cleanup_scope(scope)
        if scope not in self.host_ids_to_clean:
            self.host_ids_to_clean[scope] = set()
        self.host_ids_to_clean[scope].update(_ids_from_hosts(hosts))

    def add_groups(self, groups: GROUP_OR_GROUPS, scope: str = "function") -> None:
        _check_cleanup_scope(scope)
        if scope not in self.group_ids_to_clean:
            self.group_ids_to_clean[scope] = set()
        self.group_ids_to_clean[scope].update(_ids_from_groups(groups))

    def add_exports(self, export_ids: set[str], scope: str = "function") -> None:
        _check_cleanup_scope(scope)
        if scope not in self.export_ids_to_clean:
            self.export_ids_to_clean[scope] = set()
        self.export_ids_to_clean[scope].update(export_ids)

    def add_workspaces(self, workspaces: WORKSPACE_OR_WORKSPACES, scope: str = "function") -> None:
        _check_cleanup_scope(scope)
        if scope not in self.workspace_ids_to_clean:
            self.workspace_ids_to_clean[scope] = set()
        self.workspace_ids_to_clean[scope].update(_ids_from_workspaces(workspaces))

    def clean_hosts(self, scope: str) -> None:
        _check_cleanup_scope(scope)
        hbi_hosts_api: HostsAPIWrapper = self.application.host_inventory.apis.hosts
        if self.host_ids_to_clean.get(scope):
            hbi_hosts_api.delete_by_id(self.host_ids_to_clean[scope], retries=100)
            self.host_ids_to_clean[scope].clear()

    def clean_groups(self, scope: str) -> None:
        _check_cleanup_scope(scope)
        hbi_groups_api: GroupsAPIWrapper = self.application.host_inventory.apis.groups
        if self.group_ids_to_clean.get(scope):
            hbi_groups_api.delete_groups(self.group_ids_to_clean[scope], retries=100)
            self.group_ids_to_clean[scope].clear()

    def clean_exports(self, scope: str) -> None:
        _check_cleanup_scope(scope)
        hbi_exports_api: ExportsAPIWrapper = self.application.host_inventory.apis.exports
        if self.export_ids_to_clean.get(scope):
            hbi_exports_api.delete_exports(self.export_ids_to_clean[scope])
            self.export_ids_to_clean[scope].clear()

    def clean_workspaces(self, scope: str) -> None:
        _check_cleanup_scope(scope)
        workspaces_api: WorkspacesAPIWrapper = self.application.host_inventory.apis.workspaces
        if self.workspace_ids_to_clean.get(scope):
            workspaces_api.delete_workspaces(self.workspace_ids_to_clean[scope])
            self.workspace_ids_to_clean[scope].clear()

    def clean_all(self, scope: str) -> None:
        self.clean_hosts(scope)
        self.clean_groups(scope)
        self.clean_exports(scope)
        self.clean_workspaces(scope)

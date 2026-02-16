# mypy: disallow-untyped-defs

from __future__ import annotations

import contextlib
import logging
from collections.abc import Collection
from collections.abc import Generator
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cached_property
from typing import Any
from typing import TypedDict

import attr
from iqe.base.modeling import BaseEntity

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.modeling.hosts_api import HOST_OR_HOSTS
from iqe_host_inventory.modeling.hosts_api import _ids_from_hosts
from iqe_host_inventory.utils import is_global_account
from iqe_host_inventory.utils.api_utils import accept_when
from iqe_host_inventory.utils.api_utils import check_org_id
from iqe_host_inventory.utils.api_utils import is_ungrouped_host
from iqe_host_inventory.utils.api_utils import set_per_page
from iqe_host_inventory.utils.datagen_utils import generate_display_name
from iqe_host_inventory_api import ApiException
from iqe_host_inventory_api import GroupOut
from iqe_host_inventory_api import GroupOutWithHostCount
from iqe_host_inventory_api import GroupQueryOutput
from iqe_host_inventory_api import GroupsApi
from iqe_host_inventory_api import HostOut

GROUP_NOT_CREATED_ERROR = Exception("Group wasn't successfully created")
GROUP_NOT_UPDATED_ERROR = Exception("Group wasn't successfully updated")
GROUP_NOT_DELETED_ERROR = Exception("Group wasn't successfully deleted")
HOSTS_NOT_ADDED_ERROR = Exception("Hosts weren't successfully added")
HOSTS_NOT_REMOVED_ERROR = Exception("Hosts weren't successfully removed")

GROUP_OR_ID = GroupOut | GroupOutWithHostCount | str
GROUP_OR_GROUPS = GROUP_OR_ID | Collection[GROUP_OR_ID]


logger = logging.getLogger(__name__)


class _GroupsIN(TypedDict, total=False):
    """hack to pass over data while openapi spec for groupIn is broken"""

    name: str
    host_ids: list[str]


@dataclass()
class GroupData:
    """Used in 'create_groups' method"""

    name: str | None = None
    hosts: HOST_OR_HOSTS | None = None


def _id_from_group(group: GROUP_OR_ID) -> str:
    return group if isinstance(group, str) else group.id


def _ids_from_groups(groups: GROUP_OR_GROUPS) -> list[str]:
    if isinstance(groups, Collection) and not isinstance(groups, str):
        return [_id_from_group(group) for group in groups]
    return [_id_from_group(groups)]


def _verify_host_count_params(
    hosts: HOST_OR_HOSTS | None = None, host_count: int | None = None
) -> None:
    """If both 'hosts' and 'host_count' are given, verify that the host_count makes sense"""
    if hosts is not None and host_count is not None:
        host_ids = _ids_from_hosts(hosts)
        if host_count != len(host_ids):
            raise ValueError(
                f"Provided host count {host_count} and number of hosts {len(host_ids)} differ"
            )


@attr.s
class GroupsAPIWrapper(BaseEntity):
    @cached_property
    def _host_inventory(self) -> ApplicationHostInventory:
        return self.application.host_inventory

    @cached_property
    def raw_api(self) -> GroupsApi:
        """
        Raw auto-generated OpenAPI client.
        Use high level API wrapper methods instead of this raw API client.
        Outside this class this should be used only for negative validation testing.
        """
        return self._host_inventory.rest_client.groups_api

    def _group_fields_match(
        self,
        group: GroupOut | GroupOutWithHostCount,
        *,
        name: str | None = None,
        hosts: HOST_OR_HOSTS | None = None,
        host_count: int | None = None,
    ) -> bool:
        _verify_host_count_params(hosts, host_count)
        if hosts is not None and host_count is None:
            host_count = len(_ids_from_hosts(hosts))

        host_ids = set(_ids_from_hosts(hosts)) if hosts is not None else None

        # Check name
        if name is not None and group.name != name:
            return False

        # Check host_count
        if (
            isinstance(group, GroupOutWithHostCount)
            and host_count is not None
            and group.host_count != host_count
        ):
            return False

        # Check hosts
        return hosts is None or set(self.get_group_host_ids(group=group)) == host_ids

    @check_org_id
    def get_groups_response(
        self,
        *,
        name: str | None = None,
        group_type: str | None = None,
        per_page: int | None = None,
        page: int | None = None,
        order_by: str | None = None,
        order_how: str | None = None,
        **api_kwargs: Any,
    ) -> GroupQueryOutput:
        """Get list of groups filtered by parameters, return OpenAPI client response

        :param str name: Filter by group name
        :param str group_type: Filter by group type
            Values: "all", "standard", "ungrouped-hosts"
            Default: "standard" (the api call will default to this)
        :param int per_page: A number of items to return per page
            Default: 50
            Max: 100
        :param int page: A page number of the items to return
            Default: 1
        :param str order_by: Ordering field name
            Valid options: name, host_count
            Default: name
        :param str order_how: Direction of the ordering
            Valid options: ASC, DESC
            Default: ASC for 'name', DESC for 'host_count'
        :return GroupQueryOutput: API response
        """
        with self._host_inventory.apis.measure_time("GET /groups"):
            return self.raw_api.api_group_get_group_list(
                name=name,
                group_type=group_type,
                per_page=per_page,
                page=page,
                order_by=order_by,
                order_how=order_how,
                **api_kwargs,
            )

    def get_groups(
        self,
        *,
        name: str | None = None,
        group_type: str | None = None,
        per_page: int | None = None,
        page: int | None = None,
        order_by: str | None = None,
        order_how: str | None = None,
        **api_kwargs: Any,
    ) -> list[GroupOutWithHostCount]:
        """Get list of groups filtered by parameters, return list of groups

        :param str name: Filter by group name
        :param str group_type: Filter by group type
            Values: "all", "standard", "ungrouped-hosts"
            Default: "standard" (the api call will default to this)
        :param int per_page: A number of items to return per page
            Default: 50
            Max: 100
        :param int page: A page number of the items to return
            Default: 1
        :param str order_by: Ordering field name
            Valid options: name, host_count
            Default: name
        :param str order_how: Direction of the ordering
            Valid options: ASC, DESC
            Default: ASC for 'name', DESC for 'host_count'
        :return list[GroupOutWithHostCount]: List of retrieved groups
        """
        return self.get_groups_response(
            name=name,
            group_type=group_type,
            per_page=per_page,
            page=page,
            order_by=order_by,
            order_how=order_how,
            **api_kwargs,
        ).results

    @check_org_id
    def get_groups_by_id_response(
        self,
        groups: GROUP_OR_GROUPS,
        *,
        per_page: int | None = None,
        page: int | None = None,
        order_by: str | None = None,
        order_how: str | None = None,
        **api_kwargs: Any,
    ) -> GroupQueryOutput:
        """Get groups by their IDs, return OpenAPI client response

        :param GROUP_OR_GROUPS groups: (required) Either a single group or a list of groups
            A group can be represented either by its ID (str) or a group object
        :param int per_page: A number of items to return per page
            Default: 50
            Max: 100
        :param int page: A page number of the items to return
            Default: 1
        :param str order_by: Ordering field name
            Valid options: name, host_count
            Default: name
        :param str order_how: Direction of the ordering
            Valid options: ASC, DESC
            Default: ASC for 'name', DESC for 'host_count'
        :return GroupQueryOutput: API response
        """
        group_ids = _ids_from_groups(groups)
        with self._host_inventory.apis.measure_time(
            "GET /groups/<group_ids>", count=len(group_ids)
        ):
            return self.raw_api.api_group_get_groups_by_id(
                group_ids,
                per_page=per_page,
                page=page,
                order_by=order_by,
                order_how=order_how,
                **api_kwargs,
            )

    def get_groups_by_id(
        self,
        groups: GROUP_OR_GROUPS,
        *,
        per_page: int | None = None,
        page: int | None = None,
        order_by: str | None = None,
        order_how: str | None = None,
        **api_kwargs: Any,
    ) -> list[GroupOutWithHostCount]:
        """Get groups by their IDs, return list of groups

        :param GROUP_OR_GROUPS groups: (required) Either a single group or a list of groups
            A group can be represented either by its ID (str) or a group object
        :param int per_page: A number of items to return per page
            Default: 50
            Max: 100
        :param int page: A page number of the items to return
            Default: 1
        :param str order_by: Ordering field name
            Valid options: name, host_count
            Default: name
        :param str order_how: Direction of the ordering
            Valid options: ASC, DESC
            Default: ASC for 'name', DESC for 'host_count'
        :return list[GroupOutWithHostCount]: Retrieved groups
        """
        group_ids = _ids_from_groups(groups)
        per_page = set_per_page(per_page, group_ids, item_name="group")
        response_groups = []

        while group_ids:
            response_groups.extend(
                self.get_groups_by_id_response(
                    group_ids[:100],
                    per_page=per_page,
                    page=page,
                    order_by=order_by,
                    order_how=order_how,
                    **api_kwargs,
                ).results
            )
            group_ids = group_ids[100:]

        return response_groups

    def get_group_by_id(self, group: GROUP_OR_ID, **api_kwargs: Any) -> GroupOutWithHostCount:
        """Get a single group by its ID

        :param GROUP_OR_ID group: (required) A single group
            A group can be represented either by its ID (str) or a group object
        :return GroupOutWithHostCount: Retrieved group
        """
        groups = self.get_groups_by_id(group, **api_kwargs)
        assert len(groups) == 1, f"Expected 1 group, got {len(groups)}: {groups}"
        return groups[0]

    def get_group_hosts(
        self, *, group: GROUP_OR_ID | None = None, group_name: str | None = None
    ) -> list[HostOut]:
        """Get hosts associated with a group

        NOTE: This uses the legacy GET /hosts?group_name=... endpoint.
        For the new GET /groups/{group_id}/hosts endpoint, use get_hosts_from_group().

        :param GROUP_OR_ID group: A single group
            A group can be represented either by its ID (str) or a group object
        :param str group_name: Group name
            Exactly one of "group" or "group_name" parameters must be provided. Not both.
        :return list[HostOut]: Hosts associated with the group
        """
        if group is not None and group_name is not None:
            raise ValueError("Provided both group and group_name. Provide only one of them.")
        if group is None and group_name is None:
            raise ValueError("Didn't provide group nor group_name. Provide one of them.")
        if group is not None:
            # Get a fresh group name in case it was changed and the object group.name is old
            group_name = self.get_group_by_id(group).name
        assert group_name is not None  # This can't happen, but we need to make mypy happy
        return self._host_inventory.apis.hosts.get_hosts(group_name=[group_name])

    def get_hosts_from_group(
        self,
        group: GROUP_OR_ID,
        *,
        display_name: str | None = None,
        fqdn: str | None = None,
        hostname_or_id: str | None = None,
        insights_id: str | None = None,
        page: int = 1,
        per_page: int = 100,
        order_by: str | None = None,
        order_how: str | None = None,
        staleness: list[str] | None = None,
        tags: list[str] | None = None,
        registered_with: list[str] | None = None,
        filter: dict[str, Any] | None = None,
    ) -> list[HostOut]:
        """Get hosts from a group using the new GET /groups/{group_id}/hosts endpoint

        This is the new dedicated endpoint for retrieving hosts from a specific group.
        It supports all standard host filtering, ordering, and pagination parameters.

        NOTE: The IQE API client must be regenerated to include this endpoint.
        Run: iqe apigen generate-api host_inventory api

        :param GROUP_OR_ID group: (required) A single group
            A group can be represented either by its ID (str) or a group object
        :param str display_name: Filter by display name (wildcard matching)
        :param str fqdn: Filter by FQDN (exact matching)
        :param str hostname_or_id: Filter by hostname or ID (wildcard matching)
        :param str insights_id: Filter by insights_id
        :param int page: Page number (1-indexed)
        :param int per_page: Number of results per page
        :param str order_by: Column to order by (e.g., 'updated', 'display_name')
        :param str order_how: Order direction ('ASC' or 'DESC')
        :param list[str] staleness: List of staleness states to include
        :param list[str] tags: List of tags to filter by
        :param list[str] registered_with: Filter by registered_with values
        :param dict filter: System profile filters
        :return list[HostOut]: Hosts in the group
        """
        group_id = _id_from_group(group)

        # Call the generated API client method
        # NOTE: This requires the API client to be regenerated with the new endpoint
        response = self.raw_api.api_host_group_get_host_list_by_group(
            group_id,
            display_name=display_name,
            fqdn=fqdn,
            hostname_or_id=hostname_or_id,
            insights_id=insights_id,
            page=page,
            per_page=per_page,
            order_by=order_by,
            order_how=order_how,
            staleness=staleness,
            tags=tags,
            registered_with=registered_with,
            filter=filter,
        )

        return response.results

    def get_group_host_ids(
        self, *, group: GROUP_OR_ID | None = None, group_name: str | None = None
    ) -> list[str]:
        """Get IDs of hosts associated with a group

        :param GROUP_OR_ID group: A single group
            A group can be represented either by its ID (str) or a group object
        :param str group_name: Group name
            Exactly one of "group" or "group_name" parameters must be provided. Not both.
        :return list[str]: Host IDs
        """
        return [host.id for host in self.get_group_hosts(group=group, group_name=group_name)]

    @check_org_id
    def create_group(
        self,
        name: str,
        *,
        hosts: HOST_OR_HOSTS | None = None,
        wait_for_created: bool = True,
        register_for_cleanup: bool = True,
        cleanup_scope: str = "function",
        **api_kwargs: Any,
    ) -> GroupOutWithHostCount:
        """Create a new group and return a response from the POST /groups endpoint

        :param str name: (required) A group name (has to be unique for each group)
        :param HOST_OR_HOSTS hosts: Either a single host or a list of hosts
            These hosts will be associated with the group
            A host can be represented either by its ID (str) or a HostWrapper or HostOut object
        :param bool wait_for_created: If True, this method will wait until the group is
            retrievable by API (it should be available instantly)
            Default: True
        :param bool register_for_cleanup: If True, the new group will be registered for a cleanup
            Note that this doesn't mean that the group will actually get cleaned up.  For
            that you have to use one of the cleanup fixtures from `fixtures/cleanup_fixtures.py`
            By selecting a proper fixture you can choose when you want the group to be deleted.
            Look at conftest.py for example usage.
            Default: True
        :param str cleanup_scope: The scope to use for cleanup.
            Possible values: "function", "class", "module", "package", "session"
            Default: "function"
        :return GroupOutWithHostCount: Created group (response from POST /groups)
        """
        group_data: _GroupsIN = {"name": name}
        if hosts is not None:
            assert not isinstance(hosts, set)
            host_ids: list[str] = _ids_from_hosts(hosts)
            group_data["host_ids"] = host_ids

        with self._host_inventory.apis.measure_time("POST /groups"):
            created_group = self.raw_api.api_group_create_group(group_data, **api_kwargs)

        if wait_for_created:
            self.wait_for_created(created_group)

        if register_for_cleanup:
            self._host_inventory.cleanup.add_groups(created_group, scope=cleanup_scope)

        return created_group

    def create_groups(
        self,
        data: Iterable[GroupData],
        *,
        wait_for_created: bool = True,
        register_for_cleanup: bool = True,
        cleanup_scope: str = "function",
        **api_kwargs: Any,
    ) -> list[GroupOutWithHostCount]:
        """Create multiple new groups and return a list of created groups

        :param Iterable[GroupData] data: (required) A sequence of data used for creating groups.
            The group data are represented by a GroupData object. If a group name is not provided,
            a random one will be generated. If hosts are not provided, the group will be empty.
        :param bool wait_for_created: If True, this method will wait until the group is
            retrievable by API (it should be available instantly)
            Default: True
        :param bool register_for_cleanup: If True, the new groups will be registered for a cleanup
            Note that this doesn't mean that the groups will actually get cleaned up.  For
            that you have to use one of the cleanup fixtures from `fixtures/cleanup_fixtures.py`
            By selecting a proper fixture you can choose when you want the group to be deleted.
            Look at conftest.py for example usage.
            Default: True
        :param str cleanup_scope: The scope to use for cleanup.
            Possible values: "function", "class", "module", "package", "session"
            Default: "function"
        :return list[GroupOutWithHostCount]: Created groups (responses from POST /groups)
        """
        groups = []
        for group_data in data:
            if group_data.name is None:
                group_data.name = generate_display_name()

            groups.append(
                self.create_group(
                    name=group_data.name,
                    hosts=group_data.hosts,
                    wait_for_created=False,
                    register_for_cleanup=register_for_cleanup,
                    cleanup_scope=cleanup_scope,
                    **api_kwargs,
                )
            )

        if wait_for_created:
            self.wait_for_created(groups)

        return groups

    def create_n_empty_groups(
        self,
        n: int,
        *,
        wait_for_created: bool = True,
        register_for_cleanup: bool = True,
        cleanup_scope: str = "function",
        **api_kwargs: Any,
    ) -> list[GroupOutWithHostCount]:
        """Create n new empty groups with random names and return a list of created groups

        :param int n: (required) A number of groups to be created
        :param bool wait_for_created: If True, this method will wait until the group is
            retrievable by API (it should be available instantly)
            Default: True
        :param bool register_for_cleanup: If True, the new groups will be registered for a cleanup
            Note that this doesn't mean that the groups will actually get cleaned up.  For
            that you have to use one of the cleanup fixtures from `fixtures/cleanup_fixtures.py`
            By selecting a proper fixture you can choose when you want the group to be deleted.
            Look at conftest.py for example usage.
            Default: True
        :param str cleanup_scope: The scope to use for cleanup.
            Possible values: "function", "class", "module", "package", "session"
            Default: "function"
        :return list[GroupOutWithHostCount]: Created groups (responses from POST /groups)
        """
        groups = [
            self.create_group(
                generate_display_name(),
                wait_for_created=False,
                register_for_cleanup=register_for_cleanup,
                cleanup_scope=cleanup_scope,
                **api_kwargs,
            )
            for _ in range(n)
        ]

        if wait_for_created:
            self.wait_for_created(groups)

        return groups

    def wait_for_created(
        self,
        groups: GROUP_OR_GROUPS,
        *,
        delay: float = 0.5,
        retries: int = 10,
        error: Exception | None = GROUP_NOT_CREATED_ERROR,
    ) -> list[GroupOutWithHostCount]:
        """Wait until the groups are successfully created and retrievable by API

        :param GROUP_OR_GROUPS groups: (required) Either a single group or a list of groups
            A group can be represented either by its ID (str) or a group object
        :param float delay: A delay in seconds between attempts to retrieve the groups
            Default: 0.5
        :param int retries: A maximum number of attempts to retrieve the groups
            Default: 10
        :param Exception error: An error to raise when the groups are not retrievable. If `None`,
            then no error will be raised and the method will finish successfully.
        :return list[GroupOutWithHostCount]: Retrieved groups
        """
        group_ids = set(_ids_from_groups(groups))

        def get_groups() -> list[GroupOutWithHostCount]:
            return self.get_groups_by_id(groups)

        def found_all(response_groups: list[GroupOutWithHostCount]) -> bool:
            found_ids = {group.id for group in response_groups}
            if found_ids == group_ids:
                return True

            logger.info(f"Group IDs missing: {group_ids - found_ids}")
            return False

        return accept_when(
            get_groups, is_valid=found_all, delay=delay, retries=retries, error=error
        )

    def verify_not_created(self, group_name: str, *, delay: float = 0.5, retries: int = 2) -> None:
        """Verify that the group was not created

        :param str group_name: (required) A name of the potentially created group
        :param float delay: A delay in seconds between group existence checks
            Default: 0.5
        :param int retries: A number of group existence checks
            Default: 2
        :return None
        """

        def get_groups() -> list[GroupOutWithHostCount]:
            return self.get_groups(name=group_name)

        def found(response_groups: list[GroupOutWithHostCount]) -> bool:
            return len(response_groups) > 0

        response = accept_when(
            get_groups, is_valid=found, delay=delay, retries=retries, error=None
        )
        assert not found(response), f"Groups were unexpectedly created: {response}"

    @check_org_id
    def delete_groups_raw(self, groups: GROUP_OR_GROUPS, **api_kwargs: Any) -> None:
        """Send a DELETE /groups/<group_ids> request without exception catching or fancy logic

        :param GROUP_OR_GROUPS groups: (required) Either a single group or a list of groups
            A group can be represented either by its ID (str) or a group object
        :return None
        """
        group_ids = _ids_from_groups(groups)
        with self._host_inventory.apis.measure_time(
            "DELETE /groups/<group_ids>", count=len(group_ids)
        ):
            return self.raw_api.api_group_delete_groups(group_ids, **api_kwargs)

    def delete_groups(
        self,
        groups: GROUP_OR_GROUPS,
        *,
        wait_for_deleted: bool = True,
        delay: float = 0.5,
        retries: int = 10,
        **api_kwargs: Any,
    ) -> None:
        """Delete groups

        :param GROUP_OR_GROUPS groups: (required) Either a single group or a list of groups
            A group can be represented either by its ID (str) or a group object
        :param bool wait_for_deleted: If True, this method will wait until the groups are not
            retrievable by API (they should be deleted instantly)
            Default: True
        :param float delay: A delay in seconds between attempts to check that groups are deleted
            Default: 0.5
        :param int retries: A maximum number of attempts to check that the groups are deleted
            Default: 10
        :return None
        """
        group_ids = _ids_from_groups(groups)
        while group_ids:
            try:
                self.delete_groups_raw(group_ids[:100], **api_kwargs)
                if wait_for_deleted:
                    self.wait_for_deleted(group_ids[:100], delay=delay, retries=retries)
            except ApiException as err:
                if err.status == 404:
                    logger.info(
                        f"Couldn't delete groups {group_ids}, because they were not found."
                    )
                else:
                    raise err
            finally:
                group_ids = group_ids[100:]

    def delete_all_groups(self, *, wait_for_deleted: bool = True, **api_kwargs: Any) -> None:
        """Delete all groups on the account

        WARNING: Use this method only in ephemeral or local envs, or with separate account.
        It will delete all groups on the account, which can affect tests from other plugins.

        :param bool wait_for_deleted: If True, this method will wait until the groups are not
            retrievable by API (they should be deleted instantly)
            Default: True
        :return None
        """
        if is_global_account(self.application):
            raise Exception("It's not safe to delete all groups on a global account")

        # If the env is stage or prod, or kessel phase 1 is enabled, delete all workspaces first
        if (
            self.application.config.current_env.lower() in ("stage", "prod")
            or self.unleash.is_kessel_phase_1_enabled()
        ):
            self.apis.workspaces.delete_all_workspaces()

        groups = self.get_groups(per_page=100)
        while groups:
            self.delete_groups(groups, wait_for_deleted=wait_for_deleted, **api_kwargs)
            groups = self.get_groups(per_page=100)

    def wait_for_deleted(
        self,
        groups: GROUP_OR_GROUPS,
        *,
        delay: float = 0.5,
        retries: int = 10,
        error: Exception | None = GROUP_NOT_DELETED_ERROR,
    ) -> list[GroupOutWithHostCount]:
        """Wait until the groups are successfully deleted and not retrievable by API

        :param GROUP_OR_GROUPS groups: (required) Either a single group or a list of groups
            A group can be represented either by its ID (str) or a group object
        :param float delay: A delay in seconds between attempts to check that groups are deleted
            Default: 0.5
        :param int retries: A maximum number of attempts to check that the groups are deleted
            Default: 10
        :param Exception error: An error to raise when the groups are not deleted. If `None`,
            then no error will be raised and the method will finish successfully.
        :return list[GroupOutWithHostCount]: A list of not deleted groups
        """

        def get_groups() -> list[GroupOutWithHostCount]:
            try:
                return self.get_groups_by_id(groups)
            except ApiException as e:
                if e.status == 404:
                    return []
                raise

        def all_deleted(response_groups: list[GroupOutWithHostCount]) -> bool:
            return len(response_groups) == 0

        return accept_when(
            get_groups, is_valid=all_deleted, delay=delay, retries=retries, error=error
        )

    def verify_deleted(
        self, groups: GROUP_OR_GROUPS, *, delay: float = 0.5, retries: int = 10
    ) -> None:
        """A helper for verifying that the groups have been deleted.
        Assertion error is easier to debug than a nested exception from "wait_for_deleted".

        :param GROUP_OR_GROUPS groups: (required) Either a single group or a list of groups
            A group can be represented either by its ID (str) or a group object
        :param float delay: A delay in seconds between attempts to check that group is deleted
            Default: 0.5
        :param int retries: A maximum number of attempts to check that group is deleted
            Default: 10
        :return None
        """
        response_groups = self.wait_for_deleted(groups, delay=delay, retries=retries, error=None)
        assert len(response_groups) == 0, (
            f"Groups {_ids_from_groups(response_groups)} aren't deleted"
        )

    def verify_not_deleted(
        self, groups: GROUP_OR_GROUPS, *, delay: float = 0.5, retries: int = 2
    ) -> None:
        """Verify that the groups were not deleted

        :param GROUP_OR_GROUPS groups: (required) Either a single group or a list of groups
            A group can be represented either by its ID (str) or a group object
        :param float delay: A delay in seconds between groups existence checks
            Default: 0.5
        :param int retries: A number of groups existence checks
            Default: 2
        :return None
        """
        group_ids = _ids_from_groups(groups)
        response_groups = self.wait_for_deleted(groups, delay=delay, retries=retries, error=None)
        assert len(response_groups) == len(group_ids), (
            f"Groups {set(group_ids) - set(_ids_from_groups(response_groups))} were deleted"
        )

    @check_org_id
    def patch_group(
        self,
        group: GROUP_OR_ID,
        *,
        name: str | None = None,
        hosts: HOST_OR_HOSTS | None = None,
        wait_for_updated: bool = True,
        **api_kwargs: Any,
    ) -> GroupOutWithHostCount:
        """Patch a group and return a response from the PATCH /groups/<group_id> endpoint

        :param GROUP_OR_ID group: (required) A single group to be updated
            A group can be represented either by its ID (str) or a group object
        :param str name: A group name (has to be unique for each group)
        :param HOST_OR_HOSTS hosts: Either a single host or a list of hosts
            These hosts will be associated with the group
            A host can be represented either by its ID (str) or a HostWrapper or HostOut object
        :param bool wait_for_updated: If True, this method will wait until the group is updated
            and all changes are retrievable by API (it should be updated instantly)
            Default: True
        :return GroupOutWithHostCount: Patched group (response from PATCH /groups/<group_id>)
        """
        group_id = _id_from_group(group)
        data: _GroupsIN = {}
        if name is not None:
            data["name"] = name
        if hosts is not None:
            assert not isinstance(hosts, set)
            data["host_ids"] = _ids_from_hosts(hosts)

        with self._host_inventory.apis.measure_time("PATCH /groups/<group_id>"):
            updated_group: GroupOutWithHostCount = self.raw_api.api_group_patch_group_by_id(
                group_id, data, **api_kwargs
            )

        if wait_for_updated:
            self.wait_for_updated(group, name=name, hosts=hosts)

        return updated_group

    def wait_for_updated(
        self,
        group: GROUP_OR_ID,
        *,
        name: str | None = None,
        hosts: HOST_OR_HOSTS | None = None,
        host_count: int | None = None,
        delay: float = 0.5,
        retries: int = 10,
        error: Exception | None = GROUP_NOT_UPDATED_ERROR,
    ) -> GroupOutWithHostCount:
        """Wait until the group is successfully updated and the changes are retrievable by API

        :param GROUP_OR_ID group: (required) A single group
            A group can be represented either by its ID (str) or a group object
        :param str name: A desired group name after the update
        :param HOST_OR_HOSTS hosts: Desired hosts associated with the group after the update
            A host can be represented either by its ID (str) or a HostWrapper or HostOut object
        :param int host_count: Desired number of hosts associated with the group after the update
            If both "hosts" and "host_count" parameters are provided, they have to match
        :param float delay: A delay in seconds between attempts to retrieve the group updates
            Default: 0.5
        :param int retries: A maximum number of attempts to retrieve the group updates
            Default: 10
        :param Exception error: An error to raise when the group is not updated. If `None`,
            then no error will be raised and the method will finish successfully.
        :return GroupOutWithHostCount: Retrieved group
        """
        _verify_host_count_params(hosts, host_count)

        def get_group() -> GroupOutWithHostCount:
            return self.get_group_by_id(group)

        def updated(response_group: GroupOutWithHostCount) -> bool:
            return self._group_fields_match(
                response_group, name=name, hosts=hosts, host_count=host_count
            )

        return accept_when(get_group, is_valid=updated, delay=delay, retries=retries, error=error)

    def verify_updated(
        self,
        group: GROUP_OR_ID,
        *,
        name: str | None = None,
        hosts: HOST_OR_HOSTS | None = None,
        host_count: int | None = None,
        delay: float = 0.5,
        retries: int = 10,
    ) -> GroupOutWithHostCount:
        """A helper for verifying that the group has been updated.
        Assertion error is easier to debug than a nested exception from "wait_for_updated".

        :param GROUP_OR_ID group: (required) A single group
            A group can be represented either by its ID (str) or a group object
        :param str name: Desired group name after the update
        :param HOST_OR_HOSTS hosts: Desired hosts associated with the group after the update
            A host can be represented either by its ID (str) or a HostWrapper or HostOut object
        :param int host_count: Desired number of hosts associated with the group after the update
            If both "hosts" and "host_count" parameters are provided, they have to match
        :param float delay: A delay in seconds between attempts to retrieve the group updates
            Default: 0.5
        :param int retries: A maximum number of attempts to retrieve the group updates
            Default: 10
        :return GroupOutWithHostCount: Retrieved group
        """
        _verify_host_count_params(hosts, host_count)

        response_group = self.wait_for_updated(
            group,
            name=name,
            hosts=hosts,
            host_count=host_count,
            delay=delay,
            retries=retries,
            error=None,
        )

        if not self._group_fields_match(
            response_group, name=name, hosts=hosts, host_count=host_count
        ):
            failure_msg = f"Expected name: {name}, response name: {response_group.name}\n"
            failure_msg += (
                f"Expected host_count: {host_count}, "
                f"response host_count: {response_group.host_count}\n"
            )
            failure_msg += (
                f"Expected hosts: {_ids_from_hosts(hosts) if hosts is not None else None}, "
                f"response hosts: {self.get_group_host_ids(group=group)}\n"
            )
            raise AssertionError(f"Group {response_group.id} wasn't updated:\n{failure_msg}")

        return response_group

    def verify_not_updated(
        self,
        group: GROUP_OR_ID,
        *,
        name: str | None = None,
        hosts: HOST_OR_HOSTS | None = None,
        host_count: int | None = None,
        delay: float = 0.5,
        retries: int = 2,
    ) -> None:
        """Verify that the group was not updated

        :param GROUP_OR_ID group: (required) A single group
            A group can be represented either by its ID (str) or a group object
        :param str name: Original group name (before the update attempt)
        :param HOST_OR_HOSTS hosts: Original hosts associated with the group (before the update
            attempt).
            A host can be represented either by its ID (str) or a HostWrapper or HostOut object
        :param int host_count: Original number of hosts associated with the group (before the
            update attempt).
            If both "hosts" and "host_count" parameters are provided, they have to match
        :param float delay: A delay in seconds between group details checks
            Default: 0.5
        :param int retries: A number of group details checks
            Default: 2
        :return None
        """
        _verify_host_count_params(hosts, host_count)

        def get_group() -> GroupOutWithHostCount:
            return self.get_group_by_id(group)

        def updated(response_group: GroupOutWithHostCount) -> bool:
            return not self._group_fields_match(
                response_group, name=name, hosts=hosts, host_count=host_count
            )

        response = accept_when(
            get_group, is_valid=updated, delay=delay, retries=retries, error=None
        )

        if updated(response):
            failure_msg = f"Expected name: {name}, response name: {response.name}\n"
            failure_msg += (
                f"Expected host_count: {host_count}, response host_count: {response.host_count}\n"
            )
            failure_msg += (
                f"Expected hosts: {_ids_from_hosts(hosts) if hosts is not None else None}, "
                f"response hosts: {self.get_group_host_ids(group=group)}\n"
            )
            raise AssertionError(f"Group {response.id} was unexpectedly updated:\n{failure_msg}")

    @check_org_id
    def remove_hosts_from_group(
        self,
        group: GROUP_OR_ID,
        hosts: HOST_OR_HOSTS,
        *,
        wait_for_removed: bool = True,
        **api_kwargs: Any,
    ) -> None:
        """Remove hosts from a group

        :param GROUP_OR_ID group: (required) A single group to be updated
            A group can be represented either by its ID (str) or a group object
        :param HOST_OR_HOSTS hosts: (required) Either a single host or a list of hosts
            These hosts will be removed from the group
            A host can be represented either by its ID (str) or a HostWrapper or HostOut object
        :param bool wait_for_removed: If True, this method will wait until the hosts are removed
            from the group and the change is retrievable by API (it should be done instantly)
            Default: True
        :return None
        """
        group_id = _id_from_group(group)
        host_id_list = _ids_from_hosts(hosts)

        logger.info(f"Removing hosts {host_id_list} from group {group_id}.")
        with self._host_inventory.apis.measure_time(
            "DELETE /groups/<group_id>/hosts/<host_ids>", count=len(host_id_list)
        ):
            response = self.raw_api.api_host_group_delete_hosts_from_group(
                group_id=group_id, host_id_list=host_id_list, **api_kwargs
            )

        if wait_for_removed:
            self.wait_for_hosts_removed(hosts)

        return response

    @check_org_id
    def remove_hosts_from_multiple_groups(
        self,
        hosts: HOST_OR_HOSTS,
        *,
        wait_for_removed: bool = True,
        **api_kwargs: Any,
    ) -> None:
        """Remove hosts from any groups they are associated with

        :param HOST_OR_HOSTS hosts: (required) Either a single host or a list of hosts
            These hosts will be removed from a group, if they are associated with any
            A host can be represented either by its ID (str) or a HostWrapper or HostOut object
        :param bool wait_for_removed: If True, this method will wait until the hosts are removed
            from groups and the change is retrievable by API (it should be done instantly)
            Default: True
        :return None
        """
        host_id_list = _ids_from_hosts(hosts)

        logger.info(f"Removing hosts {host_id_list} from their groups.")
        with self._host_inventory.apis.measure_time(
            "DELETE /groups/hosts/<host_ids>", count=len(host_id_list)
        ):
            response = self.raw_api.api_group_delete_hosts_from_different_groups(
                host_id_list, **api_kwargs
            )

        if wait_for_removed:
            self.wait_for_hosts_removed(hosts)

        return response

    def wait_for_hosts_removed(
        self,
        hosts: HOST_OR_HOSTS,
        *,
        delay: float = 0.5,
        retries: int = 10,
        error: Exception | None = HOSTS_NOT_REMOVED_ERROR,
    ) -> list[HostOut]:
        """Wait until the hosts are removed from groups and the changes are retrievable by API

        :param HOST_OR_HOSTS hosts: (required) Either a single host or a list of hosts
            A host can be represented either by its ID (str) or a HostWrapper or HostOut object
        :param float delay: A delay in seconds between host groups checks
            Default: 0.5
        :param int retries: A maximum number of host groups checks
            Default: 10
        :param Exception error: An error to raise when the hosts are not removed from groups.
            If `None`, then no error will be raised and the method will finish successfully.
        :return list[HostOut]: Retrieved hosts
        """

        def get_hosts() -> list[HostOut]:
            return self._host_inventory.apis.hosts.get_hosts_by_id(hosts)

        def all_removed(response_hosts: list[HostOut]) -> bool:
            return all(is_ungrouped_host(host) for host in response_hosts)

        return accept_when(
            get_hosts, is_valid=all_removed, delay=delay, retries=retries, error=error
        )

    def verify_hosts_removed(
        self, hosts: HOST_OR_HOSTS, *, delay: float = 0.5, retries: int = 10
    ) -> None:
        """A helper for verifying that the hosts have been removed from groups.
        Assertion error is easier to debug than a nested exception from "wait_for_hosts_removed".

        :param HOST_OR_HOSTS hosts: (required) Either a single host or a list of hosts
            A host can be represented either by its ID (str) or a HostWrapper or HostOut object
        :param float delay: A delay in seconds between host groups checks
            Default: 0.5
        :param int retries: A maximum number of host groups checks
            Default: 10
        :return None
        """
        response_hosts = self.wait_for_hosts_removed(
            hosts, delay=delay, retries=retries, error=None
        )
        not_removed_hosts = [host for host in response_hosts if not (is_ungrouped_host(host))]
        assert len(not_removed_hosts) == 0, (
            f"These hosts weren't successfully removed from groups: {not_removed_hosts}"
        )

    @check_org_id
    def add_hosts_to_group(
        self, group: GROUP_OR_ID, hosts: HOST_OR_HOSTS, *, wait_for_added: bool = True
    ) -> GroupOutWithHostCount:
        """Add hosts to group

        :param GROUP_OR_ID group: (required) A single group to be updated
            A group can be represented either by its ID (str) or a group object
        :param HOST_OR_HOSTS hosts: (required) Either a single host or a list of hosts
            These hosts will be associated with the provided group
            A host can be represented either by its ID (str) or a HostWrapper or HostOut object
        :param bool wait_for_added: If True, this method will wait until the hosts are added
            to the group and the change is retrievable by API (it should be done instantly)
            Default: True
        :return GroupOutWithHostCount: The updated group
        """
        group_id = _id_from_group(group)
        host_ids = _ids_from_hosts(hosts)
        with self._host_inventory.apis.measure_time(
            "POST /groups/<group_id>/hosts", count=len(host_ids)
        ):
            updated_group: GroupOutWithHostCount = (
                self.raw_api.api_host_group_add_host_list_to_group(group_id, host_ids)
            )

        if wait_for_added:
            self.wait_for_hosts_added(group, hosts)

        return updated_group

    def wait_for_hosts_added(
        self,
        group: GROUP_OR_ID,
        hosts: HOST_OR_HOSTS,
        *,
        delay: float = 0.5,
        retries: int = 10,
        error: Exception | None = HOSTS_NOT_ADDED_ERROR,
    ) -> list[str]:
        """Wait until the hosts are added to the group and the changes are retrievable by API

        :param GROUP_OR_ID group: (required) A single group that should have been updated
            A group can be represented either by its ID (str) or a group object
        :param HOST_OR_HOSTS hosts: (required) Either a single host or a list of hosts
            A host can be represented either by its ID (str) or a HostWrapper or HostOut object
        :param float delay: A delay in seconds between group hosts checks
            Default: 0.5
        :param int retries: A maximum number of group hosts checks
            Default: 10
        :param Exception error: An error to raise when the hosts are not added to the group.
            If `None`, then no error will be raised and the method will finish successfully.
        :return list[str]: Host IDs associated with the provided group
        """
        host_ids = set(_ids_from_hosts(hosts))

        def get_host_ids() -> list[str]:
            return self.get_group_host_ids(group=group)

        def hosts_added(response_host_ids: list[str]) -> bool:
            return host_ids.issubset(set(response_host_ids))

        return accept_when(
            get_host_ids, is_valid=hosts_added, delay=delay, retries=retries, error=error
        )

    def verify_hosts_added(
        self, group: GROUP_OR_ID, hosts: HOST_OR_HOSTS, *, delay: float = 0.5, retries: int = 10
    ) -> None:
        """A helper for verifying that the hosts have been added to the group.
        Assertion error is easier to debug than a nested exception from "wait_for_hosts_added".

        :param GROUP_OR_ID group: (required) A single group that should have been updated
            A group can be represented either by its ID (str) or a group object
        :param HOST_OR_HOSTS hosts: (required) Either a single host or a list of hosts
            A host can be represented either by its ID (str) or a HostWrapper or HostOut object
        :param float delay: A delay in seconds between group hosts checks
            Default: 0.5
        :param int retries: A maximum number of group hosts checks
            Default: 10
        :return None
        """
        host_ids = set(_ids_from_hosts(hosts))

        response_host_ids = self.wait_for_hosts_added(
            group, hosts, delay=delay, retries=retries, error=None
        )
        assert host_ids.issubset(set(response_host_ids)), "Hosts weren't successfully added"

    @contextlib.contextmanager
    def verify_group_count_changed(
        self, delta: int, *, delay: float = 0.5, retries: int = 10
    ) -> Generator[None]:
        """Verify that the number of groups has changed within the context

        :param int delta: (required) A desired delta between the number of groups at the beginning
            of the context and at the end. It can be positive or negative.
        :param float delay: A delay in seconds between groups number checks
            Default: 0.5
        :param int retries: A maximum number of groups number checks
            Default: 10
        :return Generator[None]
        """

        def get_total() -> int:
            return self.get_groups_response().total

        def total_changed(current_total: int) -> bool:
            return current_total == initial_total + delta

        initial_total = get_total()
        yield

        final_total = accept_when(
            get_total, is_valid=total_changed, delay=delay, retries=retries, error=None
        )
        assert total_changed(final_total)

    @contextlib.contextmanager
    def verify_group_count_not_changed(
        self, *, delay: float = 0.5, retries: int = 2
    ) -> Generator[None]:
        """Verify that the number of groups hasn't changed within the context. We can't use
        `verify_group_count_changed(0)` because that would finish after the first check when it
        receives the same amount of groups, but we want to make sure that the number of groups
        stays the same even after some time, so we want to always do <retries> number of checks.

        :param float delay: A delay in seconds between groups number checks
            Default: 0.5
        :param int retries: A number of groups number checks
            Default: 2
        :return Generator[None]
        """

        def get_total() -> int:
            return self.get_groups_response().total

        def total_changed(current_total: int) -> bool:
            return current_total != initial_total

        initial_total = get_total()
        yield

        final_total = accept_when(
            get_total, is_valid=total_changed, delay=delay, retries=retries, error=None
        )
        assert not total_changed(final_total)

# mypy: disallow-untyped-defs

from __future__ import annotations

import logging
import math
import multiprocessing
import pprint
from collections.abc import Generator
from collections.abc import Sequence
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime
from datetime import timedelta
from functools import cached_property
from time import sleep
from typing import TYPE_CHECKING
from typing import Any
from typing import NamedTuple
from typing import TypedDict

import attr
from iqe.base.modeling import BaseEntity

from iqe_host_inventory.utils.api_utils import build_query_string
from iqe_host_inventory.utils.api_utils import check_org_id
from iqe_host_inventory_api import ApiClient
from iqe_host_inventory_api import StructuredTag

if TYPE_CHECKING:
    from iqe_host_inventory import ApplicationHostInventory

from collections.abc import Collection

from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.utils import datetimes_equal
from iqe_host_inventory.utils import is_global_account
from iqe_host_inventory.utils.api_utils import accept_when
from iqe_host_inventory.utils.api_utils import set_per_page
from iqe_host_inventory_api import ApiException
from iqe_host_inventory_api import HostIdOut
from iqe_host_inventory_api import HostOut
from iqe_host_inventory_api import HostQueryOutput
from iqe_host_inventory_api import HostsApi
from iqe_host_inventory_api import HostSystemProfileOut
from iqe_host_inventory_api import SystemProfileByHostOut
from iqe_host_inventory_api import TagCountOut
from iqe_host_inventory_api import TagsOut

HOST_NOT_CREATED_ERROR = Exception("Host wasn't successfully created")
HOST_NOT_UPDATED_ERROR = Exception("Host wasn't successfully updated")
HOST_NOT_DELETED_ERROR = Exception("Host wasn't successfully deleted")
HOST_NOT_STALENESS_ERROR = Exception("Host didn't have expected staleness")

HOST_OR_ID = HostWrapper | HostOut | str
HOST_OR_HOSTS = HOST_OR_ID | Collection[HOST_OR_ID]

logger = logging.getLogger(__name__)


def _id_from_host(host: HOST_OR_ID) -> str:
    return host if isinstance(host, str) else host.id


def _ids_from_hosts(hosts: HOST_OR_HOSTS) -> list[str]:
    if isinstance(hosts, Collection) and not isinstance(hosts, str):
        return [_id_from_host(host) for host in hosts]
    return [_id_from_host(hosts)]


class HostQueryFields(TypedDict, total=False):
    display_name: str
    ansible_host: str


class PaginationInfo(NamedTuple):
    total_items: int
    total_pages: int
    per_page: int
    pages: Sequence[int]


def _host_fields_match(
    host: HostOut | HostSystemProfileOut,
    *,
    accuracy: timedelta = timedelta(0),
    **fields: Any,
) -> bool:
    differences: dict[str, tuple[Any, Any]] = {}
    for field_name, expected_value in fields.items():
        if isinstance(host, HostOut):
            result_value = getattr(host, field_name)
        else:
            result_value = getattr(host.system_profile, field_name)

        if isinstance(result_value, datetime):
            assert isinstance(expected_value, (str, datetime))
            if not datetimes_equal(result_value, expected_value, accuracy=accuracy):
                differences[field_name] = (result_value, expected_value)
        elif result_value != expected_value:
            if hasattr(result_value, "to_dict") and result_value.to_dict() == expected_value:
                continue
            differences[field_name] = (result_value, expected_value)

    if differences:
        logger.info(
            "Found differences in fields for host %s\n %s", host.id, pprint.pformat(differences)
        )
        return False

    logger.info("Found no differences in fields for host %s\n", host.id)
    return True


def _find_facts_by_namespace(host: HostOut, namespace: str) -> dict[str, Any]:
    """Returns host facts in the namespace."""
    found_facts = []
    for facts in host.facts:
        if facts.namespace == namespace:
            found_facts.append(facts.facts)

    assert len(found_facts) == 1
    return found_facts[0]


@attr.s
class HostsAPIWrapper(BaseEntity):
    @cached_property
    def _host_inventory(self) -> ApplicationHostInventory:
        return self.application.host_inventory

    @cached_property
    def raw_api(self) -> HostsApi:
        """
        Raw auto-generated OpenAPI client.
        Use high level API wrapper methods instead of this raw API client.
        Outside this class this should be used only for negative validation testing.
        """
        return self._host_inventory.rest_client.hosts_api

    @cached_property
    def api_client(self) -> ApiClient:
        return self.application.host_inventory.rest_client.client

    @contextmanager
    def async_api(self) -> Generator[None]:
        self.raw_api.api_client.pool_threads = multiprocessing.cpu_count()
        yield
        self.raw_api.api_client.pool_threads = 1

    @check_org_id
    def get_hosts_response(
        self,
        *,
        display_name: str | None = None,
        fqdn: str | None = None,
        hostname_or_id: str | None = None,
        insights_id: str | None = None,
        subscription_manager_id: str | None = None,
        provider_id: str | None = None,
        provider_type: str | None = None,
        updated_start: str | datetime | None = None,
        updated_end: str | datetime | None = None,
        last_check_in_start: str | datetime | None = None,
        last_check_in_end: str | datetime | None = None,
        group_name: list[str] | None = None,
        group_id: list[str] | None = None,
        staleness: list[str] | None = None,
        tags: list[str] | None = None,
        registered_with: list[str] | None = None,
        system_type: list[str] | None = None,
        filter: list[str] | None = None,
        fields: list[str] | None = None,
        per_page: int | None = None,
        page: int | None = None,
        order_by: str | None = None,
        order_how: str | None = None,
        **api_kwargs: Any,
    ) -> HostQueryOutput:
        """Get list of hosts filtered by parameters, return API response

        Note: The generated openapi client doesn't work correctly with deep-object
        filter and field strings.  Thus, we need to bypass the higher-level methods
        that support these parameters.  Although queries like insights_id=<uuid>
        are processed correctly, we handle these in the same manner for consistency
        purposes.

        :param str display_name: Filter hosts by display_name
        :param str fqdn: Filter hosts by fqdn
        :param str hostname_or_id: Filter hosts by display_name, fqdn, or id
        :param str insights_id: Filter hosts by insights_id
        :param str subscription_manager_id: Filter hosts by subscription_manager_id
        :param str provider_id: Filter hosts by provider_id
        :param str provider_type: Filter hosts by provider_type
            Valid options: alibaba, aws, azure, gcp, ibm
        :param str | datetime updated_start:
            Only show hosts last modified after the given date
            Format: datetime or str in ISO 8601 datetime format
        :param str | datetime updated_end:
            Only show hosts last modified before the given date
            Format: datetime or str in ISO 8601 datetime format
        :param str | datetime last_check_in_start:
            Only show hosts last checked in after the given date
            Format: datetime or str in ISO 8601 datetime format
        :param str | datetime last_check_in_end:
            Only show hosts last checked in before the given date
            Format: datetime or str in ISO 8601 datetime format
        :param list[str] group_name: Filter hosts by group_name, uses OR logic
        :param list[str] group_id: Filter hosts by group_id (UUID), uses OR logic
        :param list[str] staleness: Filter hosts by staleness, uses OR logic
            Valid options: fresh, stale, stale_warning, unknown (doesn't do anything)
        :param list[str] tags: Filter hosts by whole tags, uses OR logic
            Format: namespace/key=value
        :param list[str] registered_with: Filter hosts by reporters, uses OR logic.
            Values starting with "!" mean NOT reported by given reporter.
            Valid options: insights, yupana, satellite, discovery, puptoo, rhsm-conduit,
                           cloud-connector, !yupana, !satellite, !discovery, !puptoo,
                           !rhsm-conduit, !cloud-connector
        :param list[str] system_type: Filter hosts by their type
            Values: [ "conventional", "bootc", "edge"]
        :param list[str] filter: List of system profile filter strings.  For fields like
            operating_system that have sub-fields, see examples for nested syntax.
            Examples:
                filter = ["[host_type]=edge"]
                filter = ["[operating_system][RHEL][version][lt][]=7.10"]
                filter = ["[operating_system][RHEL][version][gt][]=7",
                          "[operating_system][RHEL][version][lt][]=8"]
        :param str fields: List of desired system profile fields
            Example:
                fields = ["arch", "host_type"]
        :param int per_page: A number of items to return per page
            Default: 50
            Max: 100
        :param int page: A page number of the items to return
            Default: 1
        :param str order_by: Ordering field name
            Valid options: display_name, group_name, updated, operating_system
            Default: display_name
        :param str order_how: Direction of the ordering
            Valid options: ASC, DESC
            Default: ASC for display_name and group_name, DESC for update and operating_system
        :return HostQueryOutput: Response from GET /hosts
        """
        path = "/hosts"
        query = build_query_string(
            display_name=display_name,
            fqdn=fqdn,
            hostname_or_id=hostname_or_id,
            insights_id=insights_id,
            subscription_manager_id=subscription_manager_id,
            provider_id=provider_id,
            provider_type=provider_type,
            updated_start=updated_start,
            updated_end=updated_end,
            last_check_in_start=last_check_in_start,
            last_check_in_end=last_check_in_end,
            group_name=group_name,
            group_id=group_id,
            staleness=staleness,
            tags=tags,
            registered_with=registered_with,
            system_type=system_type,
            filter=filter,
            fields=fields,
            per_page=per_page,
            page=page,
            order_by=order_by,
            order_how=order_how,
            **api_kwargs,
        )

        if query:
            path += "?" + query

        return self.api_client.call_api(
            path, "GET", response_type=HostQueryOutput, _return_http_data_only=True
        )

    def get_hosts(
        self,
        *,
        display_name: str | None = None,
        fqdn: str | None = None,
        hostname_or_id: str | None = None,
        insights_id: str | None = None,
        subscription_manager_id: str | None = None,
        provider_id: str | None = None,
        provider_type: str | None = None,
        updated_start: str | datetime | None = None,
        updated_end: str | datetime | None = None,
        last_check_in_start: str | datetime | None = None,
        last_check_in_end: str | datetime | None = None,
        group_name: list[str] | None = None,
        group_id: list[str] | None = None,
        staleness: list[str] | None = None,
        tags: list[str] | None = None,
        registered_with: list[str] | None = None,
        system_type: list[str] | None = None,
        filter: list[str] | None = None,
        fields: list[str] | None = None,
        per_page: int | None = None,
        page: int | None = None,
        order_by: str | None = None,
        order_how: str | None = None,
        **api_kwargs: Any,
    ) -> list[HostOut]:
        """Get list of hosts filtered by parameters, return list of retrieved hosts

        :param str display_name: Filter hosts by display_name
        :param str fqdn: Filter hosts by fqdn
        :param str hostname_or_id: Filter hosts by display_name, fqdn, or id
        :param str insights_id: Filter hosts by insights_id
        :param str subscription_manager_id: Filter hosts by subscription_manager_id
        :param str provider_id: Filter hosts by provider_id
        :param str provider_type: Filter hosts by provider_type
            Valid options: alibaba, aws, azure, gcp, ibm
        :param str | datetime updated_start:
            Only show hosts last modified after the given date
            Format: datetime or str in ISO 8601 datetime format
        :param str | datetime updated_end:
            Only show hosts last modified before the given date
            Format: datetime or str in ISO 8601 datetime format
        :param str | datetime last_check_in_start:
            Only show hosts last checked in after the given date
            Format: datetime or str in ISO 8601 datetime format
        :param str | datetime last_check_in_end:
            Only show hosts last checked in before the given date
            Format: datetime or str in ISO 8601 datetime format
        :param list[str] group_name: Filter hosts by group_name, uses OR logic
        :param list[str] group_id: Filter hosts by group_id (UUID), uses OR logic
        :param list[str] staleness: Filter hosts by staleness, uses OR logic
            Valid options: fresh, stale, stale_warning, unknown (doesn't do anything)
        :param list[str] tags: Filter hosts by whole tags, uses OR logic
            Format: namespace/key=value
        :param list[str] registered_with: Filter hosts by reporters, uses OR logic.
            Values starting with "!" mean NOT reported by given reporter.
            Valid options: insights, yupana, satellite, discovery, puptoo, rhsm-conduit,
                           cloud-connector, !yupana, !satellite, !discovery, !puptoo,
                           !rhsm-conduit, !cloud-connector
        :param list[str] system_type: Filter hosts by their type
            Values: [ "conventional", "bootc", "edge"]
        :param list[str] filter: List of system profile filter strings.  For fields like
            operating_system that have sub-fields, see examples for nested syntax.
            Examples:
                filter = ["[host_type]=edge"]
                filter = ["[operating_system][RHEL][version][lt][]=7.10"]
                filter = ["[operating_system][RHEL][version][gt][]=7",
                          "[operating_system][RHEL][version][lt][]=8"]
        :param str fields: List of desired system profile fields
            Example:
                fields = ["arch", "host_type"]
        :param int per_page: A number of items to return per page
            Default: 50
            Max: 100
        :param int page: A page number of the items to return
            Default: 1
        :param str order_by: Ordering field name
            Valid options: display_name, group_name, updated, operating_system
            Default: display_name
        :param str order_how: Direction of the ordering
            Valid options: ASC, DESC
            Default: ASC for display_name and group_name, DESC for update and operating_system
        :return list[HostOut]: List of retrieved hosts
        """
        response = self.get_hosts_response(
            display_name=display_name,
            fqdn=fqdn,
            hostname_or_id=hostname_or_id,
            insights_id=insights_id,
            subscription_manager_id=subscription_manager_id,
            provider_id=provider_id,
            provider_type=provider_type,
            updated_start=updated_start,
            updated_end=updated_end,
            last_check_in_start=last_check_in_start,
            last_check_in_end=last_check_in_end,
            group_name=group_name,
            group_id=group_id,
            staleness=staleness,
            tags=tags,
            registered_with=registered_with,
            system_type=system_type,
            filter=filter,
            fields=fields,
            per_page=per_page,
            page=page,
            order_by=order_by,
            order_how=order_how,
            **api_kwargs,
        )

        return response.results

    def get_all_hosts(self, *, fields: list[str] | None = None) -> list[HostOut]:
        """Get list of all hosts on the current account

        :param str fields: List of desired system profile fields
            Example:
                fields = ["arch", "host_type"]
        :return list[HostOut]: List of retrieved hosts
        """
        all_hosts = []
        page = 1
        hosts = self.get_hosts(fields=fields, page=page, per_page=100)
        all_hosts.extend(hosts)
        while len(hosts) == 100:
            page += 1
            hosts = self.get_hosts(fields=fields, page=page, per_page=100)
            all_hosts.extend(hosts)
        return all_hosts

    @check_org_id
    def get_hosts_by_id_response(
        self,
        hosts: HOST_OR_HOSTS,
        *,
        fields: list[str] | None = None,
        per_page: int | None = None,
        page: int | None = None,
        order_by: str | None = None,
        order_how: str | None = None,
        **api_kwargs: Any,
    ) -> HostQueryOutput:
        """Get hosts by their IDs, return API response

        Note: The generated openapi client doesn't work correctly with deep-object
        filter and field strings.  Thus, we need to bypass the higher-level methods
        that support these parameters.

        :param HOST_OR_HOSTS hosts: (required) Either a single host or a list of hosts
            A host can be represented either by its ID (str) or a host object
        :param list[str] fields: List of desired system profile fields
            Example:
                fields = ["arch", "host_type"]
        :param int per_page: A number of items to return per page
            Default: 50
            Max: 100
        :param int page: A page number of the items to return
            Default: 1
        :param str order_by: Ordering field name
            Valid options: display_name, group_name, updated, operating_system
            Default: display_name
        :param str order_how: Direction of the ordering
            Valid options: ASC, DESC
            Default: ASC for display_name and group_name, DESC for update and operating_system
        :return HostQueryOutput: Response from GET /hosts/<host_ids>
        """
        path = "/hosts/" + ",".join(_ids_from_hosts(hosts))
        query = build_query_string(
            fields=fields,
            per_page=per_page,
            page=page,
            order_by=order_by,
            order_how=order_how,
            **api_kwargs,
        )

        if query:
            path += "?" + query

        return self.api_client.call_api(
            path, "GET", response_type=HostQueryOutput, _return_http_data_only=True
        )

    def get_hosts_by_id(
        self,
        hosts: HOST_OR_HOSTS,
        *,
        fields: list[str] | None = None,
        per_page: int | None = None,
        page: int | None = None,
        order_by: str | None = None,
        order_how: str | None = None,
        **api_kwargs: Any,
    ) -> list[HostOut]:
        """Get hosts by their IDs, return list of retrieved hosts

        :param HOST_OR_HOSTS hosts: (required) Either a single host or a list of hosts
            A host can be represented either by its ID (str) or a host object
        :param list[str] fields: List of desired system profile fields
            Example:
                fields = ["arch", "host_type"]
        :param int per_page: A number of items to return per page
            Default: 50
            Max: 100
        :param int page: A page number of the items to return
            Default: 1
        :param str order_by: Ordering field name
            Valid options: display_name, group_name, updated, operating_system
            Default: display_name
        :param str order_how: Direction of the ordering
            Valid options: ASC, DESC
            Default: ASC for display_name and group_name, DESC for update and operating_system
        :return list[HostOut]: List of retrieved hosts
        """
        host_ids = _ids_from_hosts(hosts)
        per_page = set_per_page(per_page, host_ids, item_name="host")
        response_hosts = []

        while host_ids:
            response = self.get_hosts_by_id_response(
                host_ids[:100],
                fields=fields,
                per_page=per_page,
                page=page,
                order_by=order_by,
                order_how=order_how,
                **api_kwargs,
            )
            response_hosts.extend(response.results)
            host_ids = host_ids[100:]

        return response_hosts

    def get_host_by_id(
        self,
        host: HOST_OR_ID,
        *,
        fields: list[str] | None = None,
        **api_kwargs: Any,
    ) -> HostOut:
        """Get a single host by its ID

        :param HOST_OR_ID host: (required) A single host
            A host can be represented either by its ID (str) or a host object
        :param list[str] fields: List of desired system profile fields
            Example:
                fields = ["arch", "host_type"]
        :return HostOut: Retrieved host
        """
        hosts = self.get_hosts_by_id(host, fields=fields, **api_kwargs)
        assert len(hosts) == 1, f"Expected 1 host, got {len(hosts)}: {hosts}"
        return hosts[0]

    @check_org_id
    def get_hosts_system_profile_response(
        self,
        hosts: HOST_OR_HOSTS,
        *,
        fields: list[str] | None = None,
        per_page: int | None = None,
        page: int | None = None,
        order_by: str | None = None,
        order_how: str | None = None,
        **api_kwargs: Any,
    ) -> SystemProfileByHostOut:
        """Get system profile for a host or list of hosts, return API response

        Note: The generated openapi client doesn't work correctly with deep-object
        filter and field strings.  Thus, we need to bypass the higher-level methods
        that support these parameters.

        :param HOST_OR_HOSTS hosts: (required) Either a single host or a list of hosts
            A host can be represented either by its ID (str) or a host object
        :param list[str] fields: List of desired system profile fields
            If not provided, all populated system profile fields will be returned
            Example:
                fields = ["arch", "host_type"]
        :param int per_page: Number of items to return per page
           Default: 50
           Max: 100
        :param int page: Page number of the items to return
           Default: 1
        :param str order_by: Ordering field name
            Valid options: display_name, group_name, updated, operating_system
            Default: display_name
        :param str order_how: Direction of the ordering
            Valid options: ASC, DESC
            Default: ASC for display_name and group_name, DESC for update and operating_system
        :return SystemProfileByHostOut: Response from GET /hosts/<host_ids>/system_profile
        """
        path = "/hosts/" + ",".join(_ids_from_hosts(hosts)) + "/system_profile"
        query = build_query_string(
            per_page=per_page,
            page=page,
            order_by=order_by,
            order_how=order_how,
            fields=fields,
            **api_kwargs,
        )
        if query:
            path += "?" + query

        return self.api_client.call_api(
            path, "GET", response_type=SystemProfileByHostOut, _return_http_data_only=True
        )

    def get_hosts_system_profile(
        self,
        hosts: HOST_OR_HOSTS,
        *,
        fields: list[str] | None = None,
        per_page: int | None = None,
        page: int | None = None,
        order_by: str | None = None,
        order_how: str | None = None,
        **api_kwargs: Any,
    ) -> list[HostSystemProfileOut]:
        """Get system profile for a host or list of hosts, return list of hosts with system profile

        :param HOST_OR_HOSTS hosts: (required) Either a single host or a list of hosts
            A host can be represented either by its ID (str) or a host object
        :param list[str] fields: List of desired system profile fields
            If not provided, all populated system profile fields will be returned
            Example:
                fields = ["arch", "host_type"]
        :param int per_page: Number of items to return per page
           Default: 50
           Max: 100
        :param int page: Page number of the items to return
           Default: 1
        :param str order_by: Ordering field name
            Valid options: display_name, group_name, updated, operating_system
            Default: display_name
        :param str order_how: Direction of the ordering
            Valid options: ASC, DESC
            Default: ASC for display_name and group_name, DESC for update and operating_system
        :return list[HostSystemProfileOut]:
            List of retrieved hosts with system profile
        """
        host_ids = _ids_from_hosts(hosts)
        per_page = set_per_page(per_page, host_ids, item_name="host")
        response_hosts = []

        while host_ids:
            response = self.get_hosts_system_profile_response(
                host_ids[:100],
                fields=fields,
                per_page=per_page,
                page=page,
                order_by=order_by,
                order_how=order_how,
                **api_kwargs,
            )
            response_hosts.extend(response.results)
            host_ids = host_ids[100:]

        return response_hosts

    def get_host_system_profile(
        self,
        host: HOST_OR_ID,
        *,
        fields: list[str] | None = None,
        **api_kwargs: Any,
    ) -> HostSystemProfileOut:
        """Get a single host with system profile

        :param HOST_OR_ID host: (required) A single host
            A host can be represented either by its ID (str) or a host object
        :param list[str] fields: List of desired system profile fields
            If not provided, all populated system profile fields will be returned
            Example:
                fields = ["arch", "host_type"]
        :return HostSystemProfileOut: Retrieved host with system profile
        """
        hosts = self.get_hosts_system_profile(host, fields=fields, **api_kwargs)
        assert len(hosts) == 1, f"Expected 1 host, got {len(hosts)}: {hosts}"
        return hosts[0]

    def wait_for_system_profile_updated(
        self,
        host: HOST_OR_ID,
        *,
        accuracy: timedelta = timedelta(0),
        delay: float | None = None,
        retries: int | None = None,
        error: Exception | None = HOST_NOT_UPDATED_ERROR,
        **sp_fields: Any,
    ) -> HostSystemProfileOut:
        """Wait until the system profile is successfully updated and the changes are retrievable

        :param HOST_OR_ID host: (required) A single host
            A host can be represented either by its ID (str) or a host object
        :param Any sp_fields: Desired host system profile fields after the update
        :param timedelta accuracy: Used when comparing timestamp fields
            Default: 0 (timestamps have to match)
        :param float delay: A delay in seconds between attempts to retrieve the hosts updates
            Default: 0.5
        :param int retries: A maximum number of attempts to retrieve the hosts updates
            Default: 10
        :param Exception error: An error to raise when the hosts are not updated. If `None`,
            then no error will be raised and the method will finish successfully.
        :return HostSystemProfileOut: Retrieved host with system profile
        """

        def get_host() -> HostSystemProfileOut:
            return self.get_host_system_profile(host)

        def is_valid(response_host: HostSystemProfileOut) -> bool:
            return _host_fields_match(response_host, accuracy=accuracy, **sp_fields)

        return accept_when(get_host, is_valid=is_valid, delay=delay, retries=retries, error=error)

    @check_org_id
    def get_host_exists(self, insights_id: str) -> HostIdOut:
        """Check if a host exists.  If so, return its host id.

        :param str insights_id: the host's insights id
        :return HostIdOut: Object with host ID
        """
        return self.raw_api.api_host_get_host_exists(insights_id=insights_id)

    @check_org_id
    def get_host_tags_response(
        self,
        hosts: HOST_OR_HOSTS,
        *,
        search: str | None = None,
        per_page: int | None = None,
        page: int | None = None,
        order_by: str | None = None,
        order_how: str | None = None,
        **api_kwargs: Any,
    ) -> TagsOut:
        """Get tags for a host or list of hosts, return OpenAPI client response

        :param HOST_OR_HOSTS hosts: (required) Either a single host or a list of hosts
            A host can be represented either by its ID (str) or a host object
        :param str search: Filter tags by str. It can match a tag's namespace, key, and/or value.
        :param int per_page: Number of items to return per page
           Default: 50
           Max: 100
        :param int page: Page number of the items to return
           Default: 1
        :param str order_by: Ordering field name
            Valid options: display_name, group_name, updated, operating_system
            Default: display_name
        :param str order_how: Direction of the ordering
            Valid options: ASC, DESC
            Default: ASC for display_name and group_name, DESC for update and operating_system
        :return TagsOut: Response from GET /hosts/<host_ids>/tags
        """
        host_ids = _ids_from_hosts(hosts)
        return self.raw_api.api_host_get_host_tags(
            host_ids,
            search=search,
            per_page=per_page,
            page=page,
            order_by=order_by,
            order_how=order_how,
            **api_kwargs,
        )

    def get_host_tags(
        self,
        hosts: HOST_OR_HOSTS,
        *,
        search: str | None = None,
        per_page: int | None = None,
        page: int | None = None,
        order_by: str | None = None,
        order_how: str | None = None,
        **api_kwargs: Any,
    ) -> dict[str, list[StructuredTag]]:
        """Get tags for a host or list of hosts, return tags of hosts by host IDs

        :param HOST_OR_HOSTS hosts: (required) Either a single host or a list of hosts
            A host can be represented either by its ID (str) or a host object
        :param str search: Filter tags by str. It can match a tag's namespace, key, and/or value.
        :param int per_page: Number of items to return per page
           Default: 50
           Max: 100
        :param int page: Page number of the items to return
           Default: 1
        :param str order_by: Ordering field name
            Valid options: display_name, group_name, updated, operating_system
            Default: display_name
        :param str order_how: Direction of the ordering
            Valid options: ASC, DESC
            Default: ASC for display_name and group_name, DESC for update and operating_system
        :return dict[str, list[StructuredTag]]: Key is a host ID, value is a list of tags
        """
        host_ids = _ids_from_hosts(hosts)
        per_page = set_per_page(per_page, host_ids, item_name="host")
        response_tags: dict[str, list[StructuredTag]] = {}

        while host_ids:
            current_response = self.get_host_tags_response(
                host_ids[:100],
                search=search,
                per_page=per_page,
                page=page,
                order_by=order_by,
                order_how=order_how,
                **api_kwargs,
            ).results
            response_tags = {**response_tags, **current_response}
            host_ids = host_ids[100:]

        return response_tags

    @check_org_id
    def get_host_tags_count_response(
        self,
        hosts: HOST_OR_HOSTS,
        *,
        per_page: int | None = None,
        page: int | None = None,
        order_by: str | None = None,
        order_how: str | None = None,
        **api_kwargs: Any,
    ) -> TagCountOut:
        """Get number of tags for a host or a list of hosts, return OpenAPI client response

        :param HOST_OR_HOSTS hosts: (required) Either a single host or a list of hosts
            A host can be represented either by its ID (str) or a host object
        :param int per_page: Number of items to return per page
           Default: 50
           Max: 100
        :param int page: Page number of the items to return
           Default: 1
        :param str order_by: Ordering field name
            Valid options: display_name, group_name, updated, operating_system
            Default: display_name
        :param str order_how: Direction of the ordering
            Valid options: ASC, DESC
            Default: ASC for display_name and group_name, DESC for update and operating_system
        :return TagCountOut: Response from GET /hosts/<host_ids>/tags/count
        """
        host_ids = _ids_from_hosts(hosts)
        return self.raw_api.api_host_get_host_tag_count(
            host_ids,
            per_page=per_page,
            page=page,
            order_by=order_by,
            order_how=order_how,
            **api_kwargs,
        )

    def get_host_tags_count(
        self,
        hosts: HOST_OR_HOSTS,
        *,
        per_page: int | None = None,
        page: int | None = None,
        order_by: str | None = None,
        order_how: str | None = None,
        **api_kwargs: Any,
    ) -> dict[str, int]:
        """Get number of tags for a host or a list of hosts, return number of tags by host IDs

        :param HOST_OR_HOSTS hosts: (required) Either a single host or a list of hosts
            A host can be represented either by its ID (str) or a host object
        :param int per_page: Number of items to return per page
           Default: 50
           Max: 100
        :param int page: Page number of the items to return
           Default: 1
        :param str order_by: Ordering field name
            Valid options: display_name, group_name, updated, operating_system
            Default: display_name
        :param str order_how: Direction of the ordering
            Valid options: ASC, DESC
            Default: ASC for display_name and group_name, DESC for update and operating_system
        :return dict[str, int]: Key is a host ID, value is a number of tags
        """
        host_ids = _ids_from_hosts(hosts)
        per_page = set_per_page(per_page, host_ids, item_name="host")
        response_tags_count: dict[str, int] = {}

        while host_ids:
            current_response = self.get_host_tags_count_response(
                host_ids[:100],
                per_page=per_page,
                page=page,
                order_by=order_by,
                order_how=order_how,
                **api_kwargs,
            ).results
            response_tags_count = {**response_tags_count, **current_response}
            host_ids = host_ids[100:]

        return response_tags_count

    def wait_for_created(
        self,
        hosts: HOST_OR_HOSTS,
        *,
        delay: float = 0.5,
        retries: int = 40,
        error: Exception | None = HOST_NOT_CREATED_ERROR,
    ) -> list[HostOut]:
        """Wait until the hosts are successfully created and retrievable by API

        :param HOST_OR_HOSTS hosts: (required) Either a single host or a list of hosts
            A host can be represented either by its ID (str) or a host object
        :param float delay: A delay in seconds between attempts to retrieve the hosts
            Default: 0.5
        :param int retries: A maximum number of attempts to retrieve the hosts
            Default: 10
        :param Exception error: An error to raise when the hosts are not retrievable. If `None`,
            then no error will be raised and the method will finish successfully.
        :return list[HostOut]: Retrieved hosts
        """
        host_ids = set(_ids_from_hosts(hosts))

        # With Kessel, there may a short delay before hosts are available.
        # During this window, Kessel will respond with a 403.
        def get_hosts() -> list[HostOut]:
            try:
                return self.get_hosts_by_id(hosts)
            except ApiException as exc:
                assert exc.status == 403
                return []

        def found_all(response_hosts: list[HostOut]) -> bool:
            found_ids = {host.id for host in response_hosts}
            if found_ids == host_ids:
                return True

            logger.info(f"Host IDs missing: {host_ids - found_ids}")
            return False

        return accept_when(
            get_hosts, is_valid=found_all, delay=delay, retries=retries, error=error
        )

    def wait_for_created_by_filters(
        self,
        *,
        display_name: str | None = None,
        fqdn: str | None = None,
        hostname_or_id: str | None = None,
        insights_id: str | None = None,
        provider_id: str | None = None,
        provider_type: str | None = None,
        updated_start: str | datetime | None = None,
        updated_end: str | datetime | None = None,
        last_check_in_start: str | datetime | None = None,
        last_check_in_end: str | datetime | None = None,
        group_name: list[str] | None = None,
        group_id: list[str] | None = None,
        staleness: list[str] | None = None,
        tags: list[str] | None = None,
        registered_with: list[str] | None = None,
        system_type: list[str] | None = None,
        filter: list[str] | None = None,
        delay: float = 0.5,
        retries: int = 20,
        error: Exception | None = HOST_NOT_CREATED_ERROR,
        **api_kwargs: Any,
    ) -> list[HostOut]:
        """Wait until the hosts are successfully created and retrievable by API using GET /hosts

        :param str display_name: Filter hosts by display_name
        :param str fqdn: Filter hosts by fqdn
        :param str hostname_or_id: Filter hosts by display_name, fqdn, or id
        :param str insights_id: Filter hosts by insights_id
        :param str provider_id: Filter hosts by provider_id
        :param str provider_type: Filter hosts by provider_type
            Valid options: alibaba, aws, azure, gcp, ibm
        :param str | datetime updated_start:
            Only show hosts last modified after the given date
            Format: datetime or str in ISO 8601 datetime format
        :param str | datetime updated_end:
            Only show hosts last modified before the given date
            Format: datetime or str in ISO 8601 datetime format
        :param str | datetime last_check_in_start:
            Only show hosts last checked in after the given date
            Format: datetime or str in ISO 8601 datetime format
        :param str | datetime last_check_in_end:
            Only show hosts last checked in before the given date
            Format: datetime or str in ISO 8601 datetime format
        :param list[str] group_name: Filter hosts by group_name, uses OR logic
        :param list[str] group_id: Filter hosts by group_id (UUID), uses OR logic
        :param list[str] staleness: Filter hosts by staleness, uses OR logic
            Valid options: fresh, stale, stale_warning, unknown (doesn't do anything)
        :param list[str] tags: Filter hosts by whole tags, uses OR logic
            Format: namespace/key=value
        :param list[str] registered_with: Filter hosts by reporters, uses OR logic.
            Values starting with "!" mean NOT reported by given reporter.
            Valid options: insights, yupana, satellite, discovery, puptoo, rhsm-conduit,
                           cloud-connector, !yupana, !satellite, !discovery, !puptoo,
                           !rhsm-conduit, !cloud-connector
        :param list[str] system_type: Filter hosts by their type
            Values: [ "conventional", "bootc", "edge"]
        :param list[str] filter: List of system profile filter strings.  For fields like
            operating_system that have sub-fields, see examples for nested syntax.
            Examples:
                filter = ["[host_type]=edge"]
                filter = ["[operating_system][RHEL][version][lt][]=7.10"]
                filter = ["[operating_system][RHEL][version][gt][]=7",
                          "[operating_system][RHEL][version][lt][]=8"]
        :param float delay: A delay in seconds between attempts to retrieve the hosts
            Default: 0.5
        :param int retries: A maximum number of attempts to retrieve the hosts
            Default: 10
        :param Exception error: An error to raise when the hosts are not retrievable. If `None`,
            then no error will be raised and the method will finish successfully.
        :return list[HostOut]: Retrieved hosts
        """

        def get_hosts_by_filter() -> list[HostOut]:
            return self.get_hosts(
                display_name=display_name,
                fqdn=fqdn,
                hostname_or_id=hostname_or_id,
                insights_id=insights_id,
                provider_id=provider_id,
                provider_type=provider_type,
                updated_start=updated_start,
                updated_end=updated_end,
                last_check_in_start=last_check_in_start,
                last_check_in_end=last_check_in_end,
                group_name=group_name,
                group_id=group_id,
                staleness=staleness,
                tags=tags,
                registered_with=registered_with,
                system_type=system_type,
                filter=filter,
                **api_kwargs,
            )

        def is_valid(hosts: list[HostOut]) -> bool:
            return len(hosts) > 0

        return accept_when(
            get_hosts_by_filter, is_valid=is_valid, delay=delay, retries=retries, error=error
        )

    def async_wait_for_created_by_insights_ids(
        self,
        insights_ids: list[str],
        *,
        delay: float = 1,
        retries: int = 100,
        current_attempt: int = 1,
    ) -> list[HostOut]:
        insights_ids_copy = deepcopy(insights_ids)
        hosts = []

        logger.info(f"Attempt number {current_attempt} to retrieve the hosts")
        with self.async_api():
            threads = []
            for insights_id in insights_ids_copy:
                thread = self.raw_api.api_host_get_host_list(
                    insights_id=insights_id, async_req=True
                )
                threads.append(thread)

            for thread in threads:
                response = thread.get()
                if response.count == 1:
                    host = response.results[0]
                    insights_ids_copy.remove(host.insights_id)
                    hosts.append(host)

            if len(insights_ids_copy) > 0 and current_attempt < retries:
                sleep(delay)
                hosts += self.async_wait_for_created_by_insights_ids(
                    insights_ids_copy,
                    delay=delay,
                    retries=retries,
                    current_attempt=current_attempt + 1,
                )

        return hosts

    def wait_for_host_exists(
        self,
        insights_ids: list[str],
        *,
        delay: float = 0.5,
        retries: int = 40,
    ) -> list[HostIdOut]:
        host_ids = []

        # With Kessel, there may be a short delay before hosts are available.
        # During this window, if the hosts are not yet created in HBI, it will respond with a 404.
        # If the hosts are in HBI, but not synced to Kessel yet, Kessel will respond with a 403.
        for insights_id in insights_ids:
            while retries > 0:
                try:
                    response = self.get_host_exists(insights_id=insights_id)
                    host_ids.append(response.id)
                    break
                except ApiException as exc:
                    assert exc.status in (403, 404)
                    sleep(delay)
                    retries -= 1

        return host_ids

    def verify_not_created(
        self,
        *,
        display_name: str | None = None,
        fqdn: str | None = None,
        hostname_or_id: str | None = None,
        insights_id: str | None = None,
        provider_id: str | None = None,
        provider_type: str | None = None,
        updated_start: str | datetime | None = None,
        updated_end: str | datetime | None = None,
        last_check_in_start: str | datetime | None = None,
        last_check_in_end: str | datetime | None = None,
        group_name: list[str] | None = None,
        group_id: list[str] | None = None,
        staleness: list[str] | None = None,
        tags: list[str] | None = None,
        registered_with: list[str] | None = None,
        system_type: list[str] | None = None,
        filter: list[str] | None = None,
        delay: float = 0.5,
        retries: int = 2,
        **api_kwargs: Any,
    ) -> None:
        """Verify that hosts were not created

        :param str display_name: Filter hosts by display_name
        :param str fqdn: Filter hosts by fqdn
        :param str hostname_or_id: Filter hosts by display_name, fqdn, or id
        :param str insights_id: Filter hosts by insights_id
        :param str provider_id: Filter hosts by provider_id
        :param str provider_type: Filter hosts by provider_type
            Valid options: alibaba, aws, azure, gcp, ibm
        :param str | datetime updated_start:
            Only show hosts last modified after the given date
            Format: datetime or str in ISO 8601 datetime format
        :param str | datetime updated_end:
            Only show hosts last modified before the given date
            Format: datetime or str in ISO 8601 datetime format
        :param str | datetime last_check_in_start:
            Only show hosts last checked in after the given date
            Format: datetime or str in ISO 8601 datetime format
        :param str | datetime last_check_in_end:
            Only show hosts last checked in before the given date
            Format: datetime or str in ISO 8601 datetime format
        :param list[str] group_name: Filter hosts by group_name, uses OR logic
        :param list[str] group_id: Filter hosts by group_id (UUID), uses OR logic
        :param list[str] staleness: Filter hosts by staleness, uses OR logic
            Valid options: fresh, stale, stale_warning, unknown (doesn't do anything)
        :param list[str] tags: Filter hosts by whole tags, uses OR logic
            Format: namespace/key=value
        :param list[str] registered_with: Filter hosts by reporters, uses OR logic.
            Values starting with "!" mean NOT reported by given reporter.
            Valid options: insights, yupana, satellite, discovery, puptoo, rhsm-conduit,
                           cloud-connector, !yupana, !satellite, !discovery, !puptoo,
                           !rhsm-conduit, !cloud-connector
        :param list[str] system_type: Filter hosts by their type
            Values: [ "conventional", "bootc", "edge"]
        :param list[str] filter: List of system profile filter strings.  For fields like
            operating_system that have sub-fields, see examples for nested syntax.
            Examples:
                filter = ["[host_type]=edge"]
                filter = ["[operating_system][RHEL][version][lt][]=7.10"]
                filter = ["[operating_system][RHEL][version][gt][]=7",
                          "[operating_system][RHEL][version][lt][]=8"]
        :param float delay: A delay in seconds between host existence checks
            Default: 0.5
        :param int retries: A number of host existence checks
            Default: 2
        :return None
        """
        response_hosts = self.wait_for_created_by_filters(
            display_name=display_name,
            fqdn=fqdn,
            hostname_or_id=hostname_or_id,
            insights_id=insights_id,
            provider_id=provider_id,
            provider_type=provider_type,
            updated_start=updated_start,
            updated_end=updated_end,
            last_check_in_start=last_check_in_start,
            last_check_in_end=last_check_in_end,
            group_name=group_name,
            group_id=group_id,
            staleness=staleness,
            tags=tags,
            registered_with=registered_with,
            system_type=system_type,
            delay=delay,
            retries=retries,
            error=None,
            **api_kwargs,
        )
        assert len(response_hosts) == 0, f"Hosts were unexpectedly created: {response_hosts}"

    @check_org_id
    def patch_hosts(
        self,
        hosts: HOST_OR_HOSTS,
        *,
        display_name: str | None = None,
        ansible_host: str | None = None,
        wait_for_updated: bool = True,
        **api_kwargs: Any,
    ) -> None:
        """Update host's display_name or ansible_host via PATCH /hosts/<host_ids> endpoint

        :param HOST_OR_HOSTS hosts: (required) Either a single host or a list of hosts
            A host can be represented either by its ID (str) or a host object
        :param str display_name: Desired new host's display_name
        :param str ansible_host: Desired new host's ansible_host
        :param bool wait_for_updated: If True, this method will wait until the host is updated
            and all changes are retrievable by API (it should be updated instantly)
            Default: True
        :return None
        """
        host_ids = _ids_from_hosts(hosts)
        data: HostQueryFields = {}
        if display_name is not None:
            data["display_name"] = display_name
        if ansible_host is not None:
            data["ansible_host"] = ansible_host

        response = self.raw_api.api_host_patch_host_by_id(host_ids, data, **api_kwargs)

        if wait_for_updated:
            for host_id in host_ids:
                self.wait_for_updated(host_id, **data)

        return response

    def wait_for_updated(
        self,
        hosts: HOST_OR_HOSTS,
        *,
        accuracy: timedelta = timedelta(0),
        delay: float = 0.5,
        retries: int = 10,
        error: Exception | None = HOST_NOT_UPDATED_ERROR,
        **fields: Any,
    ) -> list[HostOut]:
        """Wait until the hosts are successfully updated and the changes are retrievable by API

        :param HOST_OR_HOSTS hosts: (required) Either a single host or a list of hosts
            A host can be represented either by its ID (str) or a host object
        :param Any fields: Desired host fields after the update
        :param timedelta accuracy: Used when comparing timestamp fields
            Default: 0 (timestamps have to match)
        :param float delay: A delay in seconds between attempts to retrieve the hosts updates
            Default: 0.5
        :param int retries: A maximum number of attempts to retrieve the hosts updates
            Default: 10
        :param Exception error: An error to raise when the hosts are not updated. If `None`,
            then no error will be raised and the method will finish successfully.
        :return list[HostOut]: Retrieved hosts
        """

        def get_hosts() -> list[HostOut]:
            return self.get_hosts_by_id(hosts)

        def all_updated(response_hosts: list[HostOut]) -> bool:
            return all(
                _host_fields_match(host, accuracy=accuracy, **fields) for host in response_hosts
            )

        return accept_when(
            get_hosts, is_valid=all_updated, delay=delay, retries=retries, error=error
        )

    def verify_not_updated(
        self,
        hosts: HOST_OR_HOSTS,
        *,
        accuracy: timedelta = timedelta(0),
        delay: float = 0.5,
        retries: int = 2,
        **fields: Any,
    ) -> None:
        """Verify that the hosts were not updated

        :param HOST_OR_HOSTS hosts: (required) Either a single host or a list of hosts
            A host can be represented either by its ID (str) or a host object
        :param Any fields: Original host fields (before the update attempt)
        :param timedelta accuracy: Used when comparing timestamp fields
            Default: 0 (timestamps have to match)
        :param float delay: A delay in seconds between host fields checks
            Default: 0.5
        :param int retries: A number of host fields checks
            Default: 2
        :return None
        """

        def get_hosts() -> list[HostOut]:
            return self.get_hosts_by_id(hosts)

        def some_updated(response_hosts: list[HostOut]) -> bool:
            return any(
                not _host_fields_match(host, accuracy=accuracy, **fields)
                for host in response_hosts
            )

        response = accept_when(
            get_hosts, is_valid=some_updated, delay=delay, retries=retries, error=None
        )
        assert not some_updated(response), f"Some hosts were unexpectedly updated: {response}"

    @check_org_id
    def merge_facts(
        self,
        hosts: HOST_OR_HOSTS,
        namespace: str,
        facts: dict[str, Any],
        *,
        wait_for_updated: bool = True,
        **api_kwargs: Any,
    ) -> None:
        """Merge existing host's facts with new ones via PATCH /hosts/<host_ids>/facts/<namespace>

        :param HOST_OR_HOSTS hosts: (required) Either a single host or a list of hosts
            A host can be represented either by its ID (str) or a host object
        :param str namespace: (required) Namespace of facts to be updated
        :param dict[str, Any] facts: (required) A dict of new facts to be merged with the existing
            facts in the namespace
        :param bool wait_for_updated: If True, this method will wait until the host is updated
            and all changes are retrievable by API (it should be updated instantly)
            Default: True
        :return None
        """
        host_ids = _ids_from_hosts(hosts)
        response = self.raw_api.api_host_merge_facts(
            host_ids, namespace=namespace, body=facts, **api_kwargs
        )

        if wait_for_updated:
            self.wait_for_facts_merged(host_ids, namespace, facts)

        return response

    def wait_for_facts_merged(
        self,
        hosts: HOST_OR_HOSTS,
        namespace: str,
        facts: dict[str, Any],
        *,
        delay: float = 0.5,
        retries: int = 10,
        error: Exception | None = HOST_NOT_UPDATED_ERROR,
    ) -> list[HostOut]:
        """Wait until the host facts are successfully updated and the changes are retrievable

        :param HOST_OR_HOSTS hosts: (required) Either a single host or a list of hosts
            A host can be represented either by its ID (str) or a host object
        :param str namespace: (required) Namespace of facts to be updated
        :param dict[str, Any] facts: (required) A desired new facts to be merged with the existing
            facts in the namespace after the update
        :param float delay: A delay in seconds between attempts to retrieve the hosts updates
            Default: 0.5
        :param int retries: A maximum number of attempts to retrieve the hosts updates
            Default: 10
        :param Exception error: An error to raise when the hosts are not updated. If `None`,
            then no error will be raised and the method will finish successfully.
        :return list[HostOut]: Retrieved hosts
        """

        def get_hosts() -> list[HostOut]:
            return self.get_hosts_by_id(hosts)

        def are_updated(response_hosts: list[HostOut]) -> bool:
            for host in response_hosts:
                # new facts needs to be a subset of host's facts
                if not (facts.items() <= _find_facts_by_namespace(host, namespace).items()):
                    return False
            return True

        return accept_when(
            get_hosts, is_valid=are_updated, delay=delay, retries=retries, error=error
        )

    @check_org_id
    def replace_facts(
        self,
        hosts: HOST_OR_HOSTS,
        namespace: str,
        facts: dict[str, Any],
        *,
        wait_for_updated: bool = True,
        **api_kwargs: Any,
    ) -> None:
        """Replace existing host's facts with new ones via PUT /hosts/<host_ids>/facts/<namespace>

        :param HOST_OR_HOSTS hosts: (required) Either a single host or a list of hosts
            A host can be represented either by its ID (str) or a host object
        :param str namespace: (required) Namespace of facts to be updated
        :param dict[str, Any] facts: (required) A dict of new facts to replace the existing
            facts in the namespace
        :param bool wait_for_updated: If True, this method will wait until the host is updated
            and all changes are retrievable by API (it should be updated instantly)
            Default: True
        :return None
        """
        host_ids = _ids_from_hosts(hosts)
        response = self.raw_api.api_host_replace_facts(
            host_ids, namespace=namespace, body=facts, **api_kwargs
        )

        if wait_for_updated:
            self.wait_for_facts_replaced(host_ids, namespace, facts)

        return response

    def wait_for_facts_replaced(
        self,
        hosts: HOST_OR_HOSTS,
        namespace: str,
        facts: dict[str, Any],
        *,
        delay: float = 0.5,
        retries: int = 10,
        error: Exception | None = HOST_NOT_UPDATED_ERROR,
    ) -> list[HostOut]:
        """Wait until the host facts are successfully updated and the changes are retrievable

        :param HOST_OR_HOSTS hosts: (required) Either a single host or a list of hosts
            A host can be represented either by its ID (str) or a host object
        :param str namespace: (required) Namespace of facts to be updated
        :param dict[str, Any] facts: (required) A desired new facts to replace the existing
            facts in the namespace after the update
        :param float delay: A delay in seconds between attempts to retrieve the hosts updates
            Default: 0.5
        :param int retries: A maximum number of attempts to retrieve the hosts updates
            Default: 10
        :param Exception error: An error to raise when the hosts are not updated. If `None`,
            then no error will be raised and the method will finish successfully.
        :return list[HostOut]: Retrieved hosts
        """

        def get_hosts() -> list[HostOut]:
            return self.get_hosts_by_id(hosts)

        def are_updated(response_hosts: list[HostOut]) -> bool:
            for host in response_hosts:
                if facts != _find_facts_by_namespace(host, namespace):
                    return False
            return True

        return accept_when(
            get_hosts, is_valid=are_updated, delay=delay, retries=retries, error=error
        )

    @check_org_id
    def delete_by_id_raw(self, hosts: HOST_OR_HOSTS, **api_kwargs: Any) -> None:
        """Send a DELETE /hosts/<host_ids> request without exception catching or fancy logic

        :param HOST_OR_HOSTS hosts: (required) Either a single host or a list of hosts
            A host can be represented either by its ID (str) or a host object
        :return None
        """
        host_ids = _ids_from_hosts(hosts)
        return self.raw_api.api_host_delete_host_by_id(host_id_list=host_ids, **api_kwargs)

    def delete_by_id(
        self,
        hosts: HOST_OR_HOSTS,
        *,
        wait_for_deleted: bool = True,
        delay: float = 0.5,
        retries: int = 10,
        **api_kwargs: Any,
    ) -> None:
        """Delete hosts by their IDs

        :param HOST_OR_HOSTS hosts: (required) Either a single host or a list of hosts
            A host can be represented either by its ID (str) or a host object
        :param bool wait_for_deleted: If True, this method will wait until the hosts are not
            retrievable by API (they should be deleted instantly)
            Default: True
        :param float delay: A delay in seconds between attempts to check that the hosts are deleted
            Default: 0.5
        :param int retries: A maximum number of attempts to check that the hosts are deleted
            Default: 10
        :return None
        """
        host_ids = _ids_from_hosts(hosts)
        while host_ids:
            try:
                self.delete_by_id_raw(host_ids[0], **api_kwargs)
            except ApiException as err:
                if err.status == 404:
                    logger.info(
                        f"Couldn't delete host {host_ids[0]}, because it was not found in HBI."
                    )
                else:
                    raise err
            finally:
                host_ids.pop(0)

        if wait_for_deleted:
            self.wait_for_deleted(hosts, delay=delay, retries=retries)

    def wait_for_deleted(
        self,
        hosts: HOST_OR_HOSTS,
        *,
        delay: float = 0.5,
        retries: int = 10,
        error: Exception | None = HOST_NOT_DELETED_ERROR,
    ) -> list[HostOut]:
        """Wait until the hosts are successfully deleted and not retrievable by API

        :param HOST_OR_HOSTS hosts: (required) Either a single host or a list of hosts
            A host can be represented either by its ID (str) or a host object
        :param float delay: A delay in seconds between attempts to check that the hosts are deleted
            Default: 0.5
        :param int retries: A maximum number of attempts to check that the hosts are deleted
            Default: 10
        :param Exception error: An error to raise when the hosts are not deleted. If `None`,
            then no error will be raised and the method will finish successfully.
        :return list[HostOut]: A list of not deleted hosts
        """

        host_ids = _ids_from_hosts(hosts)

        # With Kessel, there may a short delay before hosts are deleted.
        def get_hosts() -> list[HostOut]:
            not_deleted_hosts = []
            for host_id in deepcopy(host_ids):
                try:
                    response_hosts = self.get_hosts_by_id(host_id)
                    if response_hosts:
                        assert len(response_hosts) == 1
                        not_deleted_hosts.append(response_hosts[0])
                    else:
                        host_ids.remove(host_id)
                except ApiException as exc:
                    assert exc.status == 404
                    host_ids.remove(host_id)
            return not_deleted_hosts

        def are_deleted(response_hosts: list[HostOut]) -> bool:
            return len(response_hosts) == 0

        return accept_when(
            get_hosts, is_valid=are_deleted, delay=delay, retries=retries, error=error
        )

    def verify_not_deleted(
        self, hosts: HOST_OR_HOSTS, *, delay: float = 0.5, retries: int = 2
    ) -> None:
        """Verify that the hosts were not deleted

        :param HOST_OR_HOSTS hosts: (required) Either a single host or a list of hosts
            A host can be represented either by its ID (str) or a host object
        :param float delay: A delay in seconds between hosts existence checks
            Default: 0.5
        :param int retries: A number of hosts existence checks
            Default: 2
        :return None
        """
        host_ids = _ids_from_hosts(hosts)
        response_hosts = self.wait_for_deleted(hosts, delay=delay, retries=retries, error=None)
        assert len(response_hosts) == len(host_ids), (
            f"Hosts {set(host_ids) - set(_ids_from_hosts(response_hosts))} were deleted"
        )

    @check_org_id
    def delete_filtered(
        self,
        *,
        display_name: str | None = None,
        fqdn: str | None = None,
        hostname_or_id: str | None = None,
        insights_id: str | None = None,
        subscription_manager_id: str | None = None,
        provider_id: str | None = None,
        provider_type: str | None = None,
        updated_start: str | datetime | None = None,
        updated_end: str | datetime | None = None,
        last_check_in_start: str | datetime | None = None,
        last_check_in_end: str | datetime | None = None,
        group_name: list[str] | None = None,
        group_id: list[str] | None = None,
        staleness: list[str] | None = None,
        tags: list[str] | None = None,
        registered_with: list[str] | None = None,
        system_type: list[str] | None = None,
        filter: list[str] | None = None,
        wait_for_deleted: bool = True,
        **api_kwargs: Any,
    ) -> None:
        """Delete hosts by filters. At least one filter has to be provided, otherwise the request
        fails. If you want to delete all hosts, use 'confirm_delete_all' instead.

        Note: The generated openapi client doesn't work correctly with deep-object
        filter and field strings.  Thus, we need to bypass the higher-level methods
        that support these parameters.  Although queries like insights_id=<uuid>
        are processed correctly, we handle these in the same manner for consistency
        purposes.

        :param str display_name: Filter hosts by display_name
        :param str fqdn: Filter hosts by fqdn
        :param str hostname_or_id: Filter hosts by display_name, fqdn, or id
        :param str insights_id: Filter hosts by insights_id
        :param str subscription_manager_id: Filter hosts by subscription_manager_id
        :param str provider_id: Filter hosts by provider_id
        :param str provider_type: Filter hosts by provider_type
            Valid options: alibaba, aws, azure, gcp, ibm
        :param str | datetime updated_start:
            Only show hosts last modified after the given date
            Format: datetime or str in ISO 8601 datetime format
        :param str | datetime updated_end:
            Only show hosts last modified before the given date
            Format: datetime or str in ISO 8601 datetime format
        :param str | datetime last_check_in_start:
            Only show hosts last checked in after the given date
            Format: datetime or str in ISO 8601 datetime format
        :param str | datetime last_check_in_end:
            Only show hosts last checked in before the given date
            Format: datetime or str in ISO 8601 datetime format
        :param list[str] group_name: Filter hosts by group_name, uses OR logic
        :param list[str] group_id: Filter hosts by group_id (UUID), uses OR logic
        :param list[str] staleness: Filter hosts by staleness, uses OR logic
            Valid options: fresh, stale, stale_warning, unknown (doesn't do anything)
        :param list[str] tags: Filter hosts by whole tags, uses OR logic
            Format: namespace/key=value
        :param list[str] registered_with: Filter hosts by reporters, uses OR logic.
            Values starting with "!" mean NOT reported by given reporter.
            Valid options: insights, yupana, satellite, discovery, puptoo, rhsm-conduit,
                           cloud-connector, !yupana, !satellite, !discovery, !puptoo,
                           !rhsm-conduit, !cloud-connector
        :param list[str] system_type: Filter hosts by their type
            Values: [ "conventional", "bootc", "edge"]
        :param list[str] filter: List of system profile filter strings.  For fields like
            operating_system that have sub-fields, see examples for nested syntax.
            Examples:
                filter = ["[host_type]=edge"]
                filter = ["[operating_system][RHEL][version][lt][]=7.10"]
                filter = ["[operating_system][RHEL][version][gt][]=7",
                          "[operating_system][RHEL][version][lt][]=8"]
        :param bool wait_for_deleted: If True, this method will wait until the hosts are not
            retrievable by API (they should be deleted instantly)
            Default: True
        :return None
        """
        path = "/hosts"
        query = build_query_string(
            display_name=display_name,
            fqdn=fqdn,
            hostname_or_id=hostname_or_id,
            insights_id=insights_id,
            subscription_manager_id=subscription_manager_id,
            provider_id=provider_id,
            provider_type=provider_type,
            updated_start=updated_start,
            updated_end=updated_end,
            last_check_in_start=last_check_in_start,
            last_check_in_end=last_check_in_end,
            group_name=group_name,
            group_id=group_id,
            staleness=staleness,
            tags=tags,
            registered_with=registered_with,
            system_type=system_type,
            filter=filter,
            **api_kwargs,
        )

        if query:
            path += "?" + query

        response = self.api_client.call_api(path, "DELETE", _return_http_data_only=True)

        if wait_for_deleted:
            self.wait_for_deleted_filtered(
                display_name=display_name,
                fqdn=fqdn,
                hostname_or_id=hostname_or_id,
                insights_id=insights_id,
                subscription_manager_id=subscription_manager_id,
                provider_id=provider_id,
                provider_type=provider_type,
                updated_start=updated_start,
                updated_end=updated_end,
                last_check_in_start=last_check_in_start,
                last_check_in_end=last_check_in_end,
                group_name=group_name,
                group_id=group_id,
                staleness=staleness,
                tags=tags,
                registered_with=registered_with,
                system_type=system_type,
                filter=filter,
                **api_kwargs,
            )

        return response

    def wait_for_deleted_filtered(
        self,
        *,
        display_name: str | None = None,
        fqdn: str | None = None,
        hostname_or_id: str | None = None,
        insights_id: str | None = None,
        subscription_manager_id: str | None = None,
        provider_id: str | None = None,
        provider_type: str | None = None,
        updated_start: str | datetime | None = None,
        updated_end: str | datetime | None = None,
        last_check_in_start: str | datetime | None = None,
        last_check_in_end: str | datetime | None = None,
        group_name: list[str] | None = None,
        group_id: list[str] | None = None,
        staleness: list[str] | None = None,
        tags: list[str] | None = None,
        registered_with: list[str] | None = None,
        system_type: list[str] | None = None,
        filter: list[str] | None = None,
        delay: float = 0.5,
        retries: int = 10,
        error: Exception | None = HOST_NOT_DELETED_ERROR,
        **api_kwargs: Any,
    ) -> list[HostOut]:
        """Wait until the hosts are successfully deleted and not retrievable by API

        :param str display_name: Filter hosts by display_name
        :param str fqdn: Filter hosts by fqdn
        :param str hostname_or_id: Filter hosts by display_name, fqdn, or id
        :param str insights_id: Filter hosts by insights_id
        :param str subscription_manager_id: Filter hosts by subscription_manager_id
        :param str provider_id: Filter hosts by provider_id
        :param str provider_type: Filter hosts by provider_type
            Valid options: alibaba, aws, azure, gcp, ibm
        :param str | datetime updated_start:
            Only show hosts last modified after the given date
            Format: datetime or str in ISO 8601 datetime format
        :param str | datetime updated_end:
            Only show hosts last modified before the given date
            Format: datetime or str in ISO 8601 datetime format
        :param str | datetime last_check_in_start:
            Only show hosts last checked in after the given date
            Format: datetime or str in ISO 8601 datetime format
        :param str | datetime last_check_in_end:
            Only show hosts last checked in before the given date
            Format: datetime or str in ISO 8601 datetime format
        :param list[str] group_name: Filter hosts by group_name, uses OR logic
        :param list[str] group_id: Filter hosts by group_id (UUID), uses OR logic
        :param list[str] staleness: Filter hosts by staleness, uses OR logic
            Valid options: fresh, stale, stale_warning, unknown (doesn't do anything)
        :param list[str] tags: Filter hosts by whole tags, uses OR logic
            Format: namespace/key=value
        :param list[str] registered_with: Filter hosts by reporters, uses OR logic.
            Values starting with "!" mean NOT reported by given reporter.
            Valid options: insights, yupana, satellite, discovery, puptoo, rhsm-conduit,
                           cloud-connector, !yupana, !satellite, !discovery, !puptoo,
                           !rhsm-conduit, !cloud-connector
        :param list[str] system_type: Filter hosts by their type
            Values: [ "conventional", "bootc", "edge"]
        :param list[str] filter: List of system profile filter strings.  For fields like
            operating_system that have sub-fields, see examples for nested syntax.
            Examples:
                filter = ["[host_type]=edge"]
                filter = ["[operating_system][RHEL][version][lt][]=7.10"]
                filter = ["[operating_system][RHEL][version][gt][]=7",
                          "[operating_system][RHEL][version][lt][]=8"]
        :param float delay: A delay in seconds between attempts to check that the hosts are deleted
            Default: 0.5
        :param int retries: A maximum number of attempts to check that the hosts are deleted
            Default: 10
        :param Exception error: An error to raise when the hosts are not deleted. If `None`,
            then no error will be raised and the method will finish successfully.
        :return list[HostOut]: A list of not deleted hosts
        """

        def get_hosts() -> list[HostOut]:
            return self.get_hosts(
                display_name=display_name,
                fqdn=fqdn,
                hostname_or_id=hostname_or_id,
                insights_id=insights_id,
                subscription_manager_id=subscription_manager_id,
                provider_id=provider_id,
                provider_type=provider_type,
                updated_start=updated_start,
                updated_end=updated_end,
                last_check_in_start=last_check_in_start,
                last_check_in_end=last_check_in_end,
                group_name=group_name,
                group_id=group_id,
                staleness=staleness,
                tags=tags,
                registered_with=registered_with,
                system_type=system_type,
                filter=filter,
                **api_kwargs,
            )

        def are_deleted(response_hosts: list[HostOut]) -> bool:
            return len(response_hosts) == 0

        return accept_when(
            get_hosts, is_valid=are_deleted, delay=delay, retries=retries, error=error
        )

    @check_org_id
    def delete_all(self, confirm_delete_all: Any | None = None, **api_kwargs: Any) -> None:
        """Send a DELETE /hosts/all request without account check or fancy logic.
        Should be used only for negative testing, otherwise, use 'confirm_delete_all'.

        WARNING: Use this method only in ephemeral or local envs, or with your own account.
        It will delete all hosts on the account, which can affect tests from other plugins.

        :param Any confirm_delete_all: Should normally be set to True, but any
            value is allowed for negative testing
        :return None
        """
        return self.raw_api.api_host_delete_all_hosts(
            confirm_delete_all=confirm_delete_all, **api_kwargs
        )

    def confirm_delete_all(self, *, wait_for_deleted: bool = True) -> None:
        """Delete all hosts on the account

        WARNING: Use this method only in ephemeral or local envs, or with your own account.
        It will delete all hosts on the account, which can affect tests from other plugins.

        :param bool wait_for_deleted: If True, this method will wait until the hosts are not
            retrievable by API (they should be deleted instantly)
            Default: True
        :return None
        """
        if is_global_account(self.application):
            raise Exception("It's not safe to delete all hosts on a global account")

        self.delete_all(confirm_delete_all=True)

        if wait_for_deleted:
            self.wait_for_all_deleted()

    def wait_for_all_deleted(
        self,
        delay: float = 0.5,
        retries: int = 10,
        error: Exception | None = HOST_NOT_DELETED_ERROR,
    ) -> list[HostOut]:
        """Wait until all hosts are successfully deleted and not retrievable by API

        :param float delay: A delay in seconds between attempts to check that all hosts are deleted
            Default: 0.5
        :param int retries: A maximum number of attempts to check that all hosts are deleted
            Default: 10
        :param Exception error: An error to raise when the hosts are not deleted. If `None`,
            then no error will be raised and the method will finish successfully.
        :return list[HostOut]: A list of not deleted hosts
        """

        def all_deleted(hosts: list[HostOut]) -> bool:
            return len(hosts) == 0

        return accept_when(
            self.get_hosts, is_valid=all_deleted, delay=delay, retries=retries, error=error
        )

    def verify_all_deleted(self, delay: float = 0.5, retries: int = 10) -> None:
        """A helper for verifying that all hosts have been deleted.
        Assertion error is easier to debug than a nested exception from "wait_for_all_deleted".

        :param float delay: A delay in seconds between attempts to check that all hosts are deleted
            Default: 0.5
        :param int retries: A maximum number of attempts to check that all hosts are deleted
            Default: 10
        :return None
        """
        hosts = self.wait_for_all_deleted(delay=delay, retries=retries, error=None)
        assert len(hosts) == 0, f"Hosts {set(_ids_from_hosts(hosts))} were not deleted"

    @contextmanager
    def verify_host_count_changed(
        self, delta: int, *, delay: float = 0.5, retries: int = 10
    ) -> Generator[None]:
        """Verify that the number of hosts has changed within the context

        :param int delta: (required) A desired delta between the number of hosts at the beginning
            of the context and at the end. It can be positive or negative.
        :param float delay: A delay in seconds between hosts number checks
            Default: 0.5
        :param int retries: A maximum number of hosts number checks
            Default: 10
        :return Generator[None]
        """

        def fetch_total() -> int:
            return self.get_hosts_response().total

        def total_changed(current_total: int) -> bool:
            return current_total == initial_total + delta

        initial_total = fetch_total()
        yield

        final_total = accept_when(
            fetch_total, is_valid=total_changed, delay=delay, retries=retries, error=None
        )
        assert total_changed(final_total), (
            f"Hosts count changed from {initial_total} to {final_total}, expected delta: {delta}"
        )

    @contextmanager
    def verify_host_count_not_changed(
        self, *, delay: float = 0.5, retries: int = 2
    ) -> Generator[None]:
        """Verify that the number of hosts hasn't changed within the context. We can't use
        `verify_host_count_changed(0)` because that would finish after the first check when it
        receives the same amount of hosts, but we want to make sure that the number of hosts
        stays the same even after some time, so we want to always do <retries> number of checks.

        :param float delay: A delay in seconds between hosts number checks
            Default: 0.5
        :param int retries: A number of hosts number checks
            Default: 2
        :return Generator[None]
        """

        def fetch_total() -> int:
            return self.get_hosts_response().total

        def total_changed(current_total: int) -> bool:
            return current_total != initial_total

        initial_total = fetch_total()
        yield

        final_total = accept_when(
            fetch_total, is_valid=total_changed, delay=delay, retries=retries, error=None
        )
        assert not total_changed(final_total)

    def get_host_pagination_info(self, per_page: int = 10) -> PaginationInfo:
        """Get hosts pagination info, return PaginationInfo

        :param int per_page: number of hosts per page
          Default: 10
        :return: PaginationInfo
        """
        all_hosts_data = self.get_hosts_response(per_page=per_page)

        # Calculate pages for paginating
        total_hosts = all_hosts_data.total
        total_pages = math.ceil(int(total_hosts) / int(per_page))

        return PaginationInfo(
            total_items=total_hosts,
            total_pages=total_pages,
            per_page=per_page,
            pages=range(1, total_pages + 1),
        )

    def wait_for_staleness(
        self,
        hosts: HOST_OR_HOSTS,
        staleness: str,
        *,
        delay: float = 0.5,
        retries: int = 10,
        error: Exception | None = HOST_NOT_STALENESS_ERROR,
    ) -> list[HostOut]:
        """Wait until the hosts are in the specified staleness state

        :param HOST_OR_HOSTS hosts: (required) Either a single host or a list of hosts
            A host can be represented either by its ID (str) or a host object
        :param str staleness: (required) "fresh", "stale", or "stale_warning"
        :param float delay: A delay in seconds between attempts until the hosts are in the
            expected state
            Default: 0.5
        :param int retries: A maximum number of attempts to check that the hosts are in the
            expected state
            Default: 10
        :param Exception error: An error to raise when the hosts are not in the expected state.
            If `None`, then no error will be raised and the method will finish successfully.
        :return list[HostOut]: A list of the expected hosts
        """
        host_ids = set(_ids_from_hosts(hosts))

        def get_hosts_by_staleness() -> list[HostOut]:
            return self.get_hosts(staleness=[staleness])

        def hosts_stale(response_hosts: list[HostOut]) -> bool:
            return host_ids.issubset({host.id for host in response_hosts})

        return accept_when(
            get_hosts_by_staleness, is_valid=hosts_stale, delay=delay, retries=retries, error=error
        )

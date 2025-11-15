# mypy: disallow-untyped-defs

from __future__ import annotations

import logging
from datetime import datetime
from functools import cached_property
from typing import Any

import attr
from iqe.base.modeling import BaseEntity

import iqe_host_inventory
from iqe_host_inventory.utils.api_utils import build_query_string
from iqe_host_inventory.utils.api_utils import check_org_id
from iqe_host_inventory_api import ActiveTag
from iqe_host_inventory_api import ActiveTags
from iqe_host_inventory_api import ApiClient
from iqe_host_inventory_api import TagsApi

logger = logging.getLogger(__name__)


@attr.s
class TagsAPIWrapper(BaseEntity):
    @cached_property
    def _host_inventory(self) -> iqe_host_inventory.ApplicationHostInventory:
        return self.application.host_inventory

    @cached_property
    def raw_api(self) -> TagsApi:
        """
        Raw auto-generated OpenAPI client.
        Use high level API wrapper methods instead of this raw API client.
        Outside this class this should be used only for negative validation testing.
        """
        return self._host_inventory.rest_client.tags_api

    @cached_property
    def api_client(self) -> ApiClient:
        return self.application.host_inventory.rest_client.client

    @check_org_id
    def get_tags_response(
        self,
        *,
        tags: list[str] | None = None,
        search: str | None = None,
        staleness: list[str] | None = None,
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
        registered_with: list[str] | None = None,
        system_type: list[str] | None = None,
        filter: list[str] | None = None,
        per_page: int | None = None,
        page: int | None = None,
        order_by: str | None = None,
        order_how: str | None = None,
        **api_kwargs: Any,
    ) -> ActiveTags:
        """Get list of tags filtered by parameters, return OpenAPI client response

        Note: The generated openapi client doesn't work correctly with deep-object
        filter and field strings.  Thus, we need to bypass the higher-level methods
        that support these parameters.  Although queries like insights_id=<uuid>
        are processed correctly, we handle these in the same manner for consistency
        purposes.

        :param list[str] tags: Filter by whole tags, uses OR logic
            Format: namespace/key=value
        :param str search: Filter tags by part of the tag
        :param list[str] staleness: Filter tags by staleness of associated hosts, uses OR logic
            Valid options: fresh, stale, stale_warning, unknown (doesn't do anything)
        :param str display_name: Filter tags by display_name of associated hosts
        :param str fqdn: Filter tags by fqdn of associated hosts
        :param str hostname_or_id: Filter tags by display_name, fqdn, or id of associated hosts
        :param str insights_id: Filter tags by insights_id of associated hosts
        :param str provider_id: Filter tags by provider_id of associated hosts
        :param str provider_type: Filter tags by provider_type of associated hosts
            Valid options: alibaba, aws, azure, gcp, ibm
        :param str | datetime updated_start:
            Only show tags of hosts last modified after the given date
            Format: datetime or str in ISO 8601 datetime format
        :param str | datetime updated_end:
            Only show tags of hosts last modified before the given date
            Format: datetime or str in ISO 8601 datetime format
        :param str | datetime last_check_in_start:
            Only show tags of hosts last checked in after the given date
            Format: datetime or str in ISO 8601 datetime format
        :param str | datetime last_check_in_end:
            Only show tags of hosts last checked in before the given date
            Format: datetime or str in ISO 8601 datetime format
        :param list[str] group_name: Filter tags by group_name of associated hosts, uses OR logic
        :param list[str] registered_with: Filter tags by reporters of associated hosts,
            uses OR logic. Values starting with "!" mean NOT reported by given reporter.
            Valid options: insights, yupana, satellite, discovery, puptoo, rhsm-conduit,
                           cloud-connector, !yupana, !satellite, !discovery, !puptoo,
                           !rhsm-conduit, !cloud-connector
        :param list[str] system_type: Filter tags by host's type
            Values: ["conventional", "bootc", "edge"]
        :param list[str] filter: List of system profile filter strings.  For fields like
            operating_system that have sub-fields, see examples for nested syntax.
            Examples:
                filter = ["[host_type]=edge"]
                filter = ["[operating_system][RHEL][version][lt][]=7.10"]
                filter = ["[operating_system][RHEL][version][gt][]=7",
                          "[operating_system][RHEL][version][lt][]=8"]
        :param int per_page: A number of items to return per page
            Default: 50
            Max: 100
        :param int page: A page number of the items to return
            Default: 1
        :param str order_by: Ordering field name
            Valid options: tag, count
            Default: tag
        :param str order_how: Direction of the ordering
            Valid options: ASC, DESC
            Default: ASC
        :return ActiveTags: Response from GET /tags
        """
        path = "/tags"

        query = build_query_string(
            filter=filter,
            tags=tags,
            search=search,
            staleness=staleness,
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
            registered_with=registered_with,
            system_type=system_type,
            per_page=per_page,
            page=page,
            order_by=order_by,
            order_how=order_how,
            **api_kwargs,
        )
        if query:
            path += "?" + query

        return self.api_client.call_api(path, "GET", response_type=ActiveTags)[0]

    def get_tags(
        self,
        *,
        tags: list[str] | None = None,
        search: str | None = None,
        staleness: list[str] | None = None,
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
        registered_with: list[str] | None = None,
        system_type: list[str] | None = None,
        filter: list[str] | None = None,
        per_page: int | None = None,
        page: int | None = None,
        order_by: str | None = None,
        order_how: str | None = None,
        **api_kwargs: Any,
    ) -> list[ActiveTag]:
        """Get list of tags filtered by parameters, return list of tags

        Note: The generated openapi client doesn't work correctly with deep-object
        filter and field strings.  Thus, we need to bypass the higher-level methods
        that support these parameters.  Although queries like insights_id=<uuid>
        are processed correctly, we handle these in the same manner for consistency
        purposes.

        :param list[str] tags: Filter tags by whole tags, uses OR logic
            Format: namespace/key=value
        :param str search: Filter by part of the tag
        :param list[str] staleness: Filter tags by staleness of associated hosts, uses OR logic
            Valid options: fresh, stale, stale_warning, unknown (doesn't do anything)
        :param str display_name: Filter tags by display_name of associated hosts
        :param str fqdn: Filter tags by fqdn of associated hosts
        :param str hostname_or_id: Filter tags by display_name, fqdn, or id of associated hosts
        :param str insights_id: Filter tags by insights_id of associated hosts
        :param str provider_id: Filter tags by provider_id of associated hosts
        :param str provider_type: Filter tags by provider_type of associated hosts
            Valid options: alibaba, aws, azure, gcp, ibm
        :param str | datetime updated_start:
            Only show tags of hosts last modified after the given date
            Format: datetime or str in ISO 8601 datetime format
        :param str | datetime updated_end:
            Only show tags of hosts last modified before the given date
            Format: datetime or str in ISO 8601 datetime format
        :param str | datetime last_check_in_start:
            Only show tags of hosts last checked in after the given date
            Format: datetime or str in ISO 8601 datetime format
        :param str | datetime last_check_in_end:
            Only show tags of hosts last checked in before the given date
            Format: datetime or str in ISO 8601 datetime format
        :param list[str] group_name: Filter tags by group_name of associated hosts, uses OR logic
        :param list[str] registered_with: Filter tags by reporters of associated hosts,
            uses OR logic. Values starting with "!" mean NOT reported by given reporter.
            Valid options: insights, yupana, satellite, discovery, puptoo, rhsm-conduit,
                           cloud-connector, !yupana, !satellite, !discovery, !puptoo,
                           !rhsm-conduit, !cloud-connector
        :param list[str] system_type: Filter tags by host's type
            Values: ["conventional", "bootc", "edge"]
        :param list[str] filter: List of system profile filter strings.  For fields like
            operating_system that have sub-fields, see examples for nested syntax.
            Examples:
                filter = ["[host_type]=edge"]
                filter = ["[operating_system][RHEL][version][lt][]=7.10"]
                filter = ["[operating_system][RHEL][version][gt][]=7",
                          "[operating_system][RHEL][version][lt][]=8"]
        :param int per_page: A number of items to return per page
            Default: 50
            Max: 100
        :param int page: A page number of the items to return
            Default: 1
        :param str order_by: Ordering field name
            Valid options: tag, count
            Default: tag
        :param str order_how: Direction of the ordering
            Valid options: ASC, DESC
            Default: ASC
        :return list[ActiveTag]: List of tags
        """
        return self.get_tags_response(
            tags=tags,
            search=search,
            staleness=staleness,
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
            registered_with=registered_with,
            system_type=system_type,
            per_page=per_page,
            page=page,
            order_by=order_by,
            order_how=order_how,
            filter=filter,
            **api_kwargs,
        ).results

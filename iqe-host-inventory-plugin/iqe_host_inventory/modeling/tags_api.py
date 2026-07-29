# mypy: disallow-untyped-defs

from __future__ import annotations

import logging
from datetime import datetime
from functools import cached_property
from typing import Any

import attr
import requests
from iqe.base.modeling import BaseEntity

import iqe_host_inventory
from iqe_host_inventory.modeling.base_api_wrapper import BaseAPIWrapper
from iqe_host_inventory.utils.api_utils import build_query_string

logger = logging.getLogger(__name__)


@attr.s
class TagsAPIWrapper(BaseEntity):
    @cached_property
    def _host_inventory(self) -> iqe_host_inventory.ApplicationHostInventory:
        return self.application.host_inventory

    @cached_property
    def _base_wrapper(self) -> BaseAPIWrapper:
        return BaseAPIWrapper(self.application)

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
        workspace_name: list[str] | None = None,
        workspace_id: list[str] | None = None,
        registered_with: list[str] | None = None,
        system_type: list[str] | None = None,
        filter: list[str] | None = None,
        per_page: int | None = None,
        page: int | None = None,
        order_by: str | None = None,
        order_how: str | None = None,
        **api_kwargs: Any,
    ) -> requests.Response:
        """
        GET /tags. Builds the query string manually so deep-object filter params work.

        :param filter: System profile filter strings. Nested syntax for sub-fields::

            filter = ["[host_type]=edge"]
            filter = ["[operating_system][RHEL][version][lt][]=7.10"]
            filter = ["[operating_system][RHEL][version][gt][]=7",
                        "[operating_system][RHEL][version][lt][]=8"]

        :param staleness: Uses OR logic. Valid: fresh, stale, stale_warning, unknown
        :param registered_with: Uses OR logic. Prefix with ``!`` to negate.
            Valid: insights, yupana, satellite, discovery, puptoo,
            rhsm-conduit, cloud-connector
        :param provider_type: Valid: alibaba, aws, azure, gcp, ibm
        :param system_type: Valid: conventional, bootc, edge, cluster
        :param order_by: Valid: tag, count (default: tag)
        :param order_how: Valid: ASC, DESC (default: ASC)
        :param per_page: Default 50, max 100
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
            workspace_name=workspace_name,
            workspace_id=workspace_id,
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

        with self._host_inventory.apis.measure_time("GET /tags"):
            return self._base_wrapper.get(path)

    def get_tags_json(
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
        workspace_name: list[str] | None = None,
        workspace_id: list[str] | None = None,
        registered_with: list[str] | None = None,
        system_type: list[str] | None = None,
        filter: list[str] | None = None,
        per_page: int | None = None,
        page: int | None = None,
        order_by: str | None = None,
        order_how: str | None = None,
        **api_kwargs: Any,
    ) -> dict[str, Any]:
        """GET /tags, return parsed JSON body (dict with ``count``, ``total``, ``results``).

        See :meth:`get_tags_response` for parameter details.
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
            workspace_name=workspace_name,
            workspace_id=workspace_id,
            registered_with=registered_with,
            system_type=system_type,
            filter=filter,
            per_page=per_page,
            page=page,
            order_by=order_by,
            order_how=order_how,
            **api_kwargs,
        ).json()

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
        workspace_name: list[str] | None = None,
        workspace_id: list[str] | None = None,
        registered_with: list[str] | None = None,
        system_type: list[str] | None = None,
        filter: list[str] | None = None,
        per_page: int | None = None,
        page: int | None = None,
        order_by: str | None = None,
        order_how: str | None = None,
        **api_kwargs: Any,
    ) -> list[dict[str, Any]]:
        """GET /tags, return just the ``results`` list (each item has ``tag`` and ``count``).

        See :meth:`get_tags_response` for parameter details.
        """
        return self.get_tags_json(
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
            workspace_name=workspace_name,
            workspace_id=workspace_id,
            registered_with=registered_with,
            system_type=system_type,
            filter=filter,
            per_page=per_page,
            page=page,
            order_by=order_by,
            order_how=order_how,
            **api_kwargs,
        )["results"]

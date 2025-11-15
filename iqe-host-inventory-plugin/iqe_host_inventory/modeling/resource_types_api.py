# mypy: disallow-untyped-defs

from __future__ import annotations

import logging
from functools import cached_property
from typing import TYPE_CHECKING
from typing import Any

import attr
from iqe.base.modeling import BaseEntity

from iqe_host_inventory.utils.api_utils import check_org_id
from iqe_host_inventory_api import GroupOutWithHostCount
from iqe_host_inventory_api import ResourceTypesApi
from iqe_host_inventory_api import ResourceTypesGroupsQueryOutput
from iqe_host_inventory_api import ResourceTypesOut
from iqe_host_inventory_api import ResourceTypesPaginationOutLinks
from iqe_host_inventory_api import ResourceTypesQueryOutput

if TYPE_CHECKING:
    from iqe_host_inventory import ApplicationHostInventory

logger = logging.getLogger(__name__)


@attr.s
class ResourceTypesAPIWrapper(BaseEntity):
    @cached_property
    def _host_inventory(self) -> ApplicationHostInventory:
        return self.application.host_inventory

    @cached_property
    def raw_api(self) -> ResourceTypesApi:
        """
        Raw auto-generated OpenAPI client.
        Use high level API wrapper methods instead of this raw API client.
        Outside this class this should be used only for negative validation testing.
        """
        return self._host_inventory.rest_client.resource_types_api

    @check_org_id
    def get_resource_types_response(
        self,
        *,
        page: int | None = None,
        per_page: int | None = None,
        **api_kwargs: Any,
    ) -> ResourceTypesQueryOutput:
        """Get list of Inventory RBAC resource types, return OpenAPI client response

        :param int page: A page number of the items to return
            Default: 1
        :param int per_page: A number of items to return per page
            Default: 10
            Max: 100
        :return ResourceTypesQueryOutput: Resource types OpenAPI client response
        """
        return self.raw_api.api_resource_type_get_resource_type_list(
            page=page, per_page=per_page, **api_kwargs
        )

    def get_resource_types_links(
        self,
        *,
        page: int | None = None,
        per_page: int | None = None,
        **api_kwargs: Any,
    ) -> ResourceTypesPaginationOutLinks:
        """Get pagination links for Inventory RBAC resource types, return links object

        :param int page: A page number of the items to return
            Default: 1
        :param int per_page: A number of items to return per page
            Default: 10
            Max: 100
        :return ResourceTypesPaginationOutLinks: Resource types pagination links
        """
        return self.get_resource_types_response(page=page, per_page=per_page, **api_kwargs).links

    def get_resource_types_data(
        self,
        *,
        page: int | None = None,
        per_page: int | None = None,
        **api_kwargs: Any,
    ) -> list[ResourceTypesOut]:
        """Get list of Inventory RBAC resource types, return list of resource type objects

        :param int page: A page number of the items to return
            Default: 1
        :param int per_page: A number of items to return per page
            Default: 10
            Max: 100
        :return list[ResourceTypesOut]: Resource types
        """
        return self.get_resource_types_response(page=page, per_page=per_page, **api_kwargs).data

    @check_org_id
    def get_groups_response(
        self,
        *,
        name: str | None = None,
        page: int | None = None,
        per_page: int | None = None,
        **api_kwargs: Any,
    ) -> ResourceTypesGroupsQueryOutput:
        """Get list of Inventory Groups RBAC resources, return OpenAPI client response

        :param str name: Filter by group name
        :param int page: A page number of the items to return
            Default: 1
        :param int per_page: A number of items to return per page
            Default: 10
            Max: 100
        :return ResourceTypesGroupsQueryOutput: Groups OpenAPI client response
        """
        return self.raw_api.api_resource_type_get_resource_type_groups_list(
            name=name, page=page, per_page=per_page, **api_kwargs
        )

    def get_groups_links(
        self,
        *,
        name: str | None = None,
        page: int | None = None,
        per_page: int | None = None,
        **api_kwargs: Any,
    ) -> ResourceTypesPaginationOutLinks:
        """Get pagination links for Inventory Groups RBAC resources, return links object

        :param str name: Filter by group name
        :param int page: A page number of the items to return
            Default: 1
        :param int per_page: A number of items to return per page
            Default: 10
            Max: 100
        :return ResourceTypesPaginationOutLinks: Groups pagination links
        """
        return self.get_groups_response(
            name=name, page=page, per_page=per_page, **api_kwargs
        ).links

    def get_groups_data(
        self,
        *,
        name: str | None = None,
        page: int | None = None,
        per_page: int | None = None,
        **api_kwargs: Any,
    ) -> list[GroupOutWithHostCount]:
        """Get list of Inventory Groups RBAC resources, return list of Groups resource objects

        :param str name: Filter by group name
        :param int page: A page number of the items to return
            Default: 1
        :param int per_page: A number of items to return per page
            Default: 10
            Max: 100
        :return list[GroupOutWithHostCount]: Groups
        """
        return self.get_groups_response(name=name, page=page, per_page=per_page, **api_kwargs).data

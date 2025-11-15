# mypy: disallow-untyped-defs

from __future__ import annotations

import logging
from functools import cached_property
from typing import Any

import attr
from iqe.base.modeling import BaseEntity

import iqe_host_inventory
from iqe_host_inventory.utils.api_utils import check_org_id
from iqe_host_inventory_api import SystemProfileApi
from iqe_host_inventory_api import SystemProfileOperatingSystemOut
from iqe_host_inventory_api import SystemProfileOperatingSystemOutResults
from iqe_host_inventory_api import SystemProfileSapSystemOut
from iqe_host_inventory_api import SystemProfileSapSystemOutResults

logger = logging.getLogger(__name__)


@attr.s
class SystemProfileAPIWrapper(BaseEntity):
    @cached_property
    def _host_inventory(self) -> iqe_host_inventory.ApplicationHostInventory:
        return self.application.host_inventory

    @cached_property
    def raw_api(self) -> SystemProfileApi:
        """
        Raw auto-generated OpenAPI client.
        Use high level API wrapper methods instead of this raw API client.
        Outside this class this should be used only for negative validation testing.
        """
        return self._host_inventory.rest_client.system_profile_api

    @check_org_id
    def get_operating_systems_response(
        self,
        *,
        tags: list[str] | None = None,
        staleness: list[str] | None = None,
        registered_with: list[str] | None = None,
        per_page: int | None = None,
        page: int | None = None,
        **api_kwargs: Any,
    ) -> SystemProfileOperatingSystemOut:
        """Get list of operating systems filtered by parameters, return OpenAPI client response

        :param list[str] tags: Filter OSs by whole tags of associated hosts, uses OR logic
            Format: namespace/key=value
        :param list[str] staleness: Filter OSs by staleness of associated hosts, uses OR logic
            Valid options: fresh, stale, stale_warning, unknown (doesn't do anything)
        :param list[str] registered_with: Filter OSs by reporters of associated hosts,
            uses OR logic. Values starting with "!" mean NOT reported by given reporter.
            Valid options: insights, yupana, satellite, discovery, puptoo, rhsm-conduit,
                           cloud-connector, !yupana, !satellite, !discovery, !puptoo,
                           !rhsm-conduit, !cloud-connector
        :param int per_page: A number of items to return per page
            Default: 50
            Max: 100
        :param int page: A page number of the items to return
            Default: 1
        :return SystemProfileOperatingSystemOut: Response from GET /system_profile/operating_system
        """
        return self.raw_api.api_system_profile_get_operating_system(
            tags=tags,
            staleness=staleness,
            registered_with=registered_with,
            per_page=per_page,
            page=page,
            **api_kwargs,
        )

    def get_operating_systems(
        self,
        *,
        tags: list[str] | None = None,
        staleness: list[str] | None = None,
        registered_with: list[str] | None = None,
        per_page: int | None = None,
        page: int | None = None,
        **api_kwargs: Any,
    ) -> list[SystemProfileOperatingSystemOutResults]:
        """Get list of operating systems filtered by parameters,
           return list of enumerated (number of hosts with the value) operating systems

        :param list[str] tags: Filter OSs by whole tags of associated hosts, uses OR logic
            Format: namespace/key=value
        :param list[str] staleness: Filter OSs by staleness of associated hosts, uses OR logic
            Valid options: fresh, stale, stale_warning, unknown (doesn't do anything)
        :param list[str] registered_with: Filter OSs by reporters of associated hosts,
            uses OR logic. Values starting with "!" mean NOT reported by given reporter.
            Valid options: insights, yupana, satellite, discovery, puptoo, rhsm-conduit,
                           cloud-connector, !yupana, !satellite, !discovery, !puptoo,
                           !rhsm-conduit, !cloud-connector
        :param int per_page: A number of items to return per page
            Default: 50
            Max: 100
        :param int page: A page number of the items to return
            Default: 1
        :return list[SystemProfileOperatingSystemOutResults]: Number of hosts per operating system
        """
        return self.get_operating_systems_response(
            tags=tags,
            staleness=staleness,
            registered_with=registered_with,
            per_page=per_page,
            page=page,
            **api_kwargs,
        ).results

    @check_org_id
    def get_sap_sids_response(
        self,
        *,
        search: str | None = None,
        tags: list[str] | None = None,
        staleness: list[str] | None = None,
        registered_with: list[str] | None = None,
        per_page: int | None = None,
        page: int | None = None,
        **api_kwargs: Any,
    ) -> SystemProfileSapSystemOut:
        """Get list of SAP SIDs filtered by parameters, return OpenAPI client response

        :param str search: Filter SIDs by part of the SID
        :param list[str] tags: Filter SIDs by whole tags of associated hosts, uses OR logic
            Format: namespace/key=value
        :param list[str] staleness: Filter SIDs by staleness of associated hosts, uses OR logic
            Valid options: fresh, stale, stale_warning, unknown (doesn't do anything)
        :param list[str] registered_with: Filter OS by reporters of associated hosts,
            uses OR logic. Values starting with "!" mean NOT reported by given reporter.
            Valid options: insights, yupana, satellite, discovery, puptoo, rhsm-conduit,
                           cloud-connector, !yupana, !satellite, !discovery, !puptoo,
                           !rhsm-conduit, !cloud-connector
        :param int per_page: A number of items to return per page
            Default: 50
            Max: 100
        :param int page: A page number of the items to return
            Default: 1
        :return SystemProfileSapSystemOut: Response from GET /system_profile/sap_sids
        """
        return self.raw_api.api_system_profile_get_sap_sids(
            search=search,
            tags=tags,
            staleness=staleness,
            registered_with=registered_with,
            per_page=per_page,
            page=page,
            **api_kwargs,
        )

    def get_sap_sids(
        self,
        *,
        search: str | None = None,
        tags: list[str] | None = None,
        staleness: list[str] | None = None,
        registered_with: list[str] | None = None,
        per_page: int | None = None,
        page: int | None = None,
        **api_kwargs: Any,
    ) -> list[SystemProfileSapSystemOutResults]:
        """Get list of SAP SIDs filtered by parameters,
           return list of enumerated (number of hosts with the value) SAP SIDs

        :param str search: Filter SIDs by part of the SID
        :param list[str] tags: Filter SIDs by whole tags of associated hosts, uses OR logic
            Format: namespace/key=value
        :param list[str] staleness: Filter SIDs by staleness of associated hosts, uses OR logic
            Valid options: fresh, stale, stale_warning, unknown (doesn't do anything)
        :param list[str] registered_with: Filter OS by reporters of associated hosts,
            uses OR logic. Values starting with "!" mean NOT reported by given reporter.
            Valid options: insights, yupana, satellite, discovery, puptoo, rhsm-conduit,
                           cloud-connector, !yupana, !satellite, !discovery, !puptoo,
                           !rhsm-conduit, !cloud-connector
        :param int per_page: A number of items to return per page
            Default: 50
            Max: 100
        :param int page: A page number of the items to return
            Default: 1
        :return list[SystemProfileSapSystemOutResults]: Number of hosts per SAP SID
        """
        return self.get_sap_sids_response(
            search=search,
            tags=tags,
            staleness=staleness,
            registered_with=registered_with,
            per_page=per_page,
            page=page,
            **api_kwargs,
        ).results

    @check_org_id
    def get_sap_systems_response(
        self,
        *,
        tags: list[str] | None = None,
        staleness: list[str] | None = None,
        registered_with: list[str] | None = None,
        per_page: int | None = None,
        page: int | None = None,
        **api_kwargs: Any,
    ) -> SystemProfileSapSystemOut:
        """Get enumeration of sap_system values (True or False) filtered by parameters,
           return OpenAPI client response

        :param list[str] tags: Filter SAP systems by whole tags of associated hosts, uses OR logic
            Format: namespace/key=value
        :param list[str] staleness: Filter SAP systems by staleness of associated hosts,
            uses OR logic
            Valid options: fresh, stale, stale_warning, unknown (doesn't do anything)
        :param list[str] registered_with: Filter SAP systems by reporters of associated hosts,
            uses OR logic. Values starting with "!" mean NOT reported by given reporter.
            Valid options: insights, yupana, satellite, discovery, puptoo, rhsm-conduit,
                           cloud-connector, !yupana, !satellite, !discovery, !puptoo,
                           !rhsm-conduit, !cloud-connector
        :param int per_page: A number of items to return per page
            Default: 50
            Max: 100
        :param int page: A page number of the items to return
            Default: 1
        :return: SystemProfileSapSystemOut: Response from GET /system_profile/sap_system
        """
        return self.raw_api.api_system_profile_get_sap_system(
            tags=tags,
            staleness=staleness,
            registered_with=registered_with,
            per_page=per_page,
            page=page,
            **api_kwargs,
        )

    def get_sap_systems(
        self,
        *,
        tags: list[str] | None = None,
        staleness: list[str] | None = None,
        registered_with: list[str] | None = None,
        per_page: int | None = None,
        page: int | None = None,
        **api_kwargs: Any,
    ) -> list[SystemProfileSapSystemOutResults]:
        """Get enumeration of sap_system values (True or False) filtered by parameters,
           return list of enumerated (number of hosts with the value) sap_system values

        :param list[str] tags: Filter SAP systems by whole tags of associated hosts, uses OR logic
            Format: namespace/key=value
        :param list[str] staleness: Filter SAP systems by staleness of associated hosts,
            uses OR logic
            Valid options: fresh, stale, stale_warning, unknown (doesn't do anything)
        :param list[str] registered_with: Filter SAP systems by reporters of associated hosts,
            uses OR logic. Values starting with "!" mean NOT reported by given reporter.
            Valid options: insights, yupana, satellite, discovery, puptoo, rhsm-conduit,
                           cloud-connector, !yupana, !satellite, !discovery, !puptoo,
                           !rhsm-conduit, !cloud-connector
        :param int per_page: A number of items to return per page
            Default: 50
            Max: 100
        :param int page: A page number of the items to return
            Default: 1
        :return list[SystemProfileSapSystemOutResults]: Number of hosts per sap_system value
        """
        return self.get_sap_systems_response(
            tags=tags,
            staleness=staleness,
            registered_with=registered_with,
            per_page=per_page,
            page=page,
            **api_kwargs,
        ).results

# mypy: disallow-untyped-defs

from __future__ import annotations

import logging
from datetime import datetime
from functools import cached_property
from typing import TYPE_CHECKING
from typing import Any
from urllib.parse import quote

import attr
from iqe.base.modeling import BaseEntity

from iqe_host_inventory.utils.api_utils import check_org_id
from iqe_host_inventory_api import ApiClient
from iqe_host_inventory_api import HostsApi
from iqe_host_inventory_api import HostViewHost
from iqe_host_inventory_api import HostViewQueryOutput

if TYPE_CHECKING:
    from iqe_host_inventory import ApplicationHostInventory

logger = logging.getLogger(__name__)

# Application names supported by the host-view endpoint
APP_NAMES = (
    "advisor",
    "vulnerability",
    "patch",
    "remediations",
    "compliance",
    "malware",
)

_COLLECTION_PARAMS = (
    "group_name",
    "staleness",
    "tags",
    "registered_with",
    "system_type",
)


def _build_host_view_query_string(
    fields: list[str] | None = None,
    filter: list[str] | None = None,
    **api_kwargs: Any,
) -> str:
    """Build a query string for the /beta/hosts-view endpoint.

    This helper works the same way as ``build_query_string`` in ``api_utils``
    but uses the correct deep-object prefixes for the host-view ``fields``
    and ``filter`` parameters:

    - ``fields`` entries are prefixed with ``fields``.
        Examples:
            fields=["[app_data]=true"]                   -> fields[app_data]=true
            fields=["[advisor][]=recommendations"]       -> fields[advisor][]=recommendations
    - ``filter`` entries are prefixed with ``filter``.
        Examples:
            filter=["[advisor][recommendations][gte]=5"] -> filter[advisor][recommendations][gte]=5

    All other keyword arguments are treated as flat or collection query
    parameters, identical to the regular ``build_query_string`` semantics.
    """
    query_params: list[str] = []

    for key, val in api_kwargs.items():
        if key in _COLLECTION_PARAMS and isinstance(val, (list, tuple)):
            query_params.extend(f"{quote(key)}={quote(str(v))}" for v in val if v is not None)
        elif val is not None:
            query_params.append(f"{quote(key)}={quote(str(val))}")

    if fields is not None:
        query_params.extend(f"fields{f}" for f in fields)

    if filter is not None:
        query_params.extend(f"filter{f}" for f in filter)

    return "&".join(query_params)


@attr.s
class HostViewAPIWrapper(BaseEntity):
    """Wrapper around the ``GET /beta/hosts-view`` endpoint.

    The generated OpenAPI client cannot serialize the deep-object ``fields``
    and ``filter`` query parameters correctly, so this wrapper constructs
    the raw query string and uses ``api_client.call_api`` directly — the
    same approach used by ``HostsAPIWrapper`` for the ``GET /hosts`` endpoint.
    """

    @cached_property
    def _host_inventory(self) -> ApplicationHostInventory:
        return self.application.host_inventory

    @cached_property
    def raw_api(self) -> HostsApi:
        """Raw auto-generated OpenAPI client."""
        return self._host_inventory.rest_client.hosts_api

    @cached_property
    def api_client(self) -> ApiClient:
        return self._host_inventory.rest_client.client

    # ------------------------------------------------------------------
    # Core query methods
    # ------------------------------------------------------------------

    @check_org_id
    def get_host_views_response(
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
        staleness: list[str] | None = None,
        tags: list[str] | None = None,
        registered_with: list[str] | None = None,
        system_type: list[str] | None = None,
        fields: list[str] | None = None,
        filter: list[str] | None = None,
        per_page: int | None = None,
        page: int | None = None,
        order_by: str | None = None,
        order_how: str | None = None,
        **api_kwargs: Any,
    ) -> HostViewQueryOutput:
        """Query the ``GET /beta/hosts-view`` endpoint, return the full response.

        :param str display_name: Filter hosts by display_name
        :param str fqdn: Filter hosts by fqdn
        :param str hostname_or_id: Filter hosts by display_name, fqdn, or id
        :param str insights_id: Filter hosts by insights_id
        :param str subscription_manager_id: Filter hosts by subscription_manager_id
        :param str provider_id: Filter hosts by provider_id
        :param str provider_type: Filter hosts by provider_type
        :param str | datetime updated_start: Only show hosts modified after this date
        :param str | datetime updated_end: Only show hosts modified before this date
        :param str | datetime last_check_in_start: Only show hosts last checked in after this date
        :param str | datetime last_check_in_end: Only show hosts last checked in before this date
        :param list[str] group_name: Filter hosts by group_name (OR logic)
        :param list[str] staleness: Filter hosts by staleness (OR logic)
            Valid options: fresh, stale, stale_warning, unknown
        :param list[str] tags: Filter hosts by tags (OR logic). Format: namespace/key=value
        :param list[str] registered_with: Filter hosts by reporters (OR logic)
        :param list[str] system_type: Filter hosts by type (conventional, bootc, edge)
        :param list[str] fields: Deep-object field selections for application data.
            Examples:
                fields=["[app_data]=true"]                  -> include all app data
                fields=["[advisor][]=recommendations"]      -> advisor.recommendations only
                fields=["[vulnerability][]=critical_cves",
                         "[vulnerability][]=total_cves"]    -> vuln subset
        :param list[str] filter: Deep-object filters on application data.
            Format: [app_name][field_name][operator]=value
            Operators: eq, ne, gt, lt, gte, lte, nil, not_nil
            Examples:
                filter=["[advisor][recommendations][gte]=5"]
                filter=["[vulnerability][critical_cves][gte]=1"]
        :param int per_page: Number of items per page (default: 50, max: 100)
        :param int page: Page number (default: 1)
        :param str order_by: Ordering field. Standard host fields or app fields
            e.g. "display_name", "advisor:recommendations", "vulnerability:critical_cves"
        :param str order_how: Direction: ASC or DESC
        :return HostViewQueryOutput: Full paginated response from /beta/hosts-view
        """
        path = "/beta/hosts-view"
        query = _build_host_view_query_string(
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
            staleness=staleness,
            tags=tags,
            registered_with=registered_with,
            system_type=system_type,
            fields=fields,
            filter=filter,
            per_page=per_page,
            page=page,
            order_by=order_by,
            order_how=order_how,
            **api_kwargs,
        )

        if query:
            path += "?" + query

        with self._host_inventory.apis.measure_time("GET /beta/hosts-view"):
            return self.api_client.call_api(
                path, "GET", response_type=HostViewQueryOutput, _return_http_data_only=True
            )

    def get_host_views(
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
        staleness: list[str] | None = None,
        tags: list[str] | None = None,
        registered_with: list[str] | None = None,
        system_type: list[str] | None = None,
        fields: list[str] | None = None,
        filter: list[str] | None = None,
        per_page: int | None = None,
        page: int | None = None,
        order_by: str | None = None,
        order_how: str | None = None,
        **api_kwargs: Any,
    ) -> list[HostViewHost]:
        """Query the ``GET /beta/hosts-view`` endpoint, return the list of results.

        Parameters are the same as :meth:`get_host_views_response`.

        :return list[HostViewHost]: List of host view entries.
        """
        response = self.get_host_views_response(
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
            staleness=staleness,
            tags=tags,
            registered_with=registered_with,
            system_type=system_type,
            fields=fields,
            filter=filter,
            per_page=per_page,
            page=page,
            order_by=order_by,
            order_how=order_how,
            **api_kwargs,
        )

        return response.results

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def get_host_view(
        self,
        *,
        insights_id: str | None = None,
        hostname_or_id: str | None = None,
        fields: list[str] | None = None,
        **api_kwargs: Any,
    ) -> HostViewHost:
        """Retrieve a single host from the host-view endpoint.

        :param str insights_id: Filter by insights_id
        :param str hostname_or_id: Filter by display_name, fqdn, or id
        :param list[str] fields: Deep-object field selections
        :return HostViewHost: A single host-view entry
        """
        hosts = self.get_host_views(
            insights_id=insights_id,
            hostname_or_id=hostname_or_id,
            fields=fields,
            **api_kwargs,
        )
        assert len(hosts) == 1, f"Expected 1 host, got {len(hosts)}: {hosts}"
        return hosts[0]

    def get_host_view_app_data(
        self,
        *,
        insights_id: str | None = None,
        hostname_or_id: str | None = None,
        app_name: str | None = None,
        **api_kwargs: Any,
    ) -> Any:
        """Retrieve application data for a single host.

        If *app_name* is given, returns only that application's data object.
        Otherwise returns the full ``ConsumerApplicationsData`` object.

        :param str insights_id: Filter by insights_id
        :param str hostname_or_id: Filter by display_name, fqdn, or id
        :param str app_name: Optional application name to extract (e.g. "advisor")
        :return: The app data object (or sub-object for a specific application)
        """
        host = self.get_host_view(
            insights_id=insights_id,
            hostname_or_id=hostname_or_id,
            **api_kwargs,
        )

        if app_name is not None:
            assert app_name in APP_NAMES, (
                f"Invalid app_name '{app_name}'. Must be one of {APP_NAMES}"
            )
            return getattr(host.app_data, app_name, None)

        return host.app_data

    def wait_for_host_view_app_data(
        self,
        *,
        insights_id: str | None = None,
        hostname_or_id: str | None = None,
        app_name: str,
        delay: float = 0.5,
        retries: int = 40,
        **api_kwargs: Any,
    ) -> Any:
        """Wait until application data is available for a host via /beta/hosts-view.

        This polls the endpoint until the specified application's data is non-None.

        :param str insights_id: Filter by insights_id
        :param str hostname_or_id: Filter by display_name, fqdn, or id
        :param str app_name: Application name to wait for (e.g. "advisor")
        :param float delay: Seconds between attempts (default: 0.5)
        :param int retries: Maximum number of attempts (default: 40)
        :return: The application data object once available
        :raises AssertionError: If app data is not available after all retries
        """
        from iqe_host_inventory.utils.api_utils import accept_when

        assert app_name in APP_NAMES, f"Invalid app_name '{app_name}'. Must be one of {APP_NAMES}"

        def get_app_data() -> Any:
            try:
                return self.get_host_view_app_data(
                    insights_id=insights_id,
                    hostname_or_id=hostname_or_id,
                    app_name=app_name,
                    **api_kwargs,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("get_host_view_app_data failed: %s: %s", type(exc).__name__, exc)
                return None

        def is_available(data: Any) -> bool:
            return data is not None

        return accept_when(
            get_app_data,
            is_valid=is_available,
            delay=delay,
            retries=retries,
            error=Exception(f"App data for '{app_name}' not available after {retries} retries"),
        )

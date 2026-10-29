from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class HostFilters:
    """Filters shared by host, tag, view, and export queries."""

    fqdn: str | None = None
    display_name: str | None = None
    hostname_or_id: str | None = None
    insights_id: str | None = None
    subscription_manager_id: str | None = None
    provider_id: str | None = None
    provider_type: str | None = None
    updated_start: str | None = None
    updated_end: str | None = None
    last_check_in_start: str | None = None
    last_check_in_end: str | None = None
    group_name: list[str] | None = None
    group_ids: list[str] | None = None
    tags: list[str] | None = None
    staleness: list[str] | None = None
    registered_with: list[str] | None = None
    system_type: list[str] | None = None
    query_filter: dict[str, Any] | None = None
    rbac_filter: dict[str, Any] | None = None
    recommendation_severity: list[str] | None = None
    incident_status: str | None = None
    cve_severity: list[str] | None = None
    known_exploit: str | None = None
    security_rule: str | None = None


@dataclass(slots=True)
class HostListOptions:
    """Pagination and ordering options for host list queries."""

    page: int = 1
    per_page: int = 100
    order_by: str | None = None
    order_how: str | None = None
    fields: dict[str, Any] | None = None
    get_total: bool = True

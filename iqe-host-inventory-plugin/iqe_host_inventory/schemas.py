from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Protocol

from iqe_rbac_api import AccessApi
from iqe_rbac_api import GroupApi
from iqe_rbac_api import RoleApi

from iqe_host_inventory_api.models import PerReporterStaleness

PER_REPORTER_STALENESS = dict[str, PerReporterStaleness]


class RBACRestClient(Protocol):
    access_api: AccessApi
    group_api: GroupApi
    role_api: RoleApi


def reporter_staleness_from_dict(
    source: Mapping[str, str | datetime | bool],
) -> PerReporterStaleness:
    last_check_in = source["last_check_in"]
    if isinstance(last_check_in, str):
        last_check_in = datetime.fromisoformat(last_check_in)
    stale_timestamp = source["stale_timestamp"]
    if isinstance(stale_timestamp, str):
        stale_timestamp = datetime.fromisoformat(stale_timestamp)
    check_in_succeeded = source["check_in_succeeded"]
    if isinstance(check_in_succeeded, str):
        check_in_succeeded = check_in_succeeded.lower() == "true"
    return PerReporterStaleness(
        last_check_in=last_check_in,
        stale_timestamp=stale_timestamp,
        check_in_succeeded=check_in_succeeded,
    )


def per_reporter_staleness_from_dict(
    source: dict[str, dict[str, datetime | bool]],
) -> PER_REPORTER_STALENESS:
    per_reporter_staleness: PER_REPORTER_STALENESS = {}
    for reporter, staleness in source.items():
        per_reporter_staleness[reporter] = reporter_staleness_from_dict(staleness)
    return per_reporter_staleness

"""
Inventory Views API - Host Views Endpoint

This module provides the /beta/hosts-view endpoint that returns host data
combined with application-specific metrics (Advisor, Vulnerability, etc.)
"""

import flask

from api import api_operation
from api import flask_json_response
from api import metrics
from api.host_query import staleness_timestamps
from api.host_query_db import get_host_list as get_host_list_from_db
from api.staleness_query import get_staleness_obj
from app.auth import get_current_identity
from app.auth.rbac import KesselResourceTypes
from app.instrumentation import log_get_host_list_failed
from app.logging import get_logger
from app.models import HostAppDataAdvisor
from app.models import HostAppDataCompliance
from app.models import HostAppDataImageBuilder
from app.models import HostAppDataMalware
from app.models import HostAppDataPatch
from app.models import HostAppDataRemediations
from app.models import HostAppDataVulnerability
from app.models.database import db
from app.serialization import serialize_host
from lib.middleware import access

logger = get_logger(__name__)

# Registry of app data specifications
# Each entry defines: model class, fields to extract, and any special field handlers
APP_DATA_SPECS = {
    "advisor": {
        "model": HostAppDataAdvisor,
        "fields": ("recommendations", "incidents"),
        "extra": {},
    },
    "vulnerability": {
        "model": HostAppDataVulnerability,
        "fields": (
            "total_cves",
            "critical_cves",
            "high_severity_cves",
            "cves_with_security_rules",
            "cves_with_known_exploits",
        ),
        "extra": {},
    },
    "patch": {
        "model": HostAppDataPatch,
        "fields": ("installable_advisories", "template", "rhsm_locked_version"),
        "extra": {},
    },
    "remediations": {
        "model": HostAppDataRemediations,
        "fields": ("remediations_plans",),
        "extra": {},
    },
    "compliance": {
        "model": HostAppDataCompliance,
        "fields": ("policies",),
        "extra": {
            "last_scan": lambda row: row.last_scan.isoformat() if row.last_scan else None,
        },
    },
    "malware": {
        "model": HostAppDataMalware,
        "fields": ("last_status", "last_matches"),
        "extra": {
            "last_scan": lambda row: row.last_scan.isoformat() if row.last_scan else None,
        },
    },
    "image_builder": {
        "model": HostAppDataImageBuilder,
        "fields": ("image_name", "image_status"),
        "extra": {},
    },
}


def _fetch_app_data_for_hosts(host_ids: list, org_id: str) -> dict:
    """
    Fetch application data for a list of hosts from all app data tables.

    Args:
        host_ids: List of host UUIDs to fetch data for
        org_id: Organization ID to filter by

    Returns:
        Dictionary mapping host_id (str) to their app_data dict
    """
    if not host_ids:
        return {}

    host_id_strs = [str(h) for h in host_ids]
    app_data_by_app: dict[str, dict[str, dict]] = {}

    # Fetch data from each app data table using the registry
    for app_name, spec in APP_DATA_SPECS.items():
        model = spec["model"]
        fields = spec["fields"]
        extra = spec["extra"]

        rows = (
            db.session.query(model)
            .filter(model.org_id == org_id, model.host_id.in_(host_ids))
            .all()
        )

        app_data_by_app[app_name] = {
            str(row.host_id): {
                **{field: getattr(row, field) for field in fields},
                **{name: fn(row) for name, fn in extra.items()},
            }
            for row in rows
        }

    # Build result: for each host, include only apps that have data
    result: dict[str, dict] = {}
    for host_id in host_id_strs:
        app_data = {}
        for app_name, data_dict in app_data_by_app.items():
            if host_id in data_dict:
                app_data[app_name] = data_dict[host_id]
        result[host_id] = app_data

    return result


def _build_host_view_response(total, page, per_page, host_list):
    """Build the response for the hosts-view endpoint."""
    timestamps = staleness_timestamps()
    identity = get_current_identity()
    staleness = get_staleness_obj(identity.org_id)

    host_ids = [host.id for host in host_list]
    app_data_map = _fetch_app_data_for_hosts(host_ids, identity.org_id)

    results = []
    for host in host_list:
        host_data = serialize_host(host, timestamps, False, (), staleness, None)
        host_data["app_data"] = app_data_map.get(str(host.id), {})
        results.append(host_data)

    return {
        "total": total,
        "count": len(results),
        "page": page,
        "per_page": per_page,
        "results": results,
    }


@api_operation
@access(KesselResourceTypes.HOST.view)
@metrics.api_request_time.time()
def get_host_views(  # noqa: PLR0913, PLR0917
    display_name=None,
    fqdn=None,
    hostname_or_id=None,
    insights_id=None,
    subscription_manager_id=None,
    provider_id=None,
    provider_type=None,
    updated_start=None,
    updated_end=None,
    last_check_in_start=None,
    last_check_in_end=None,
    group_name=None,
    branch_id=None,  # noqa: ARG001
    page=1,
    per_page=50,
    order_by=None,
    order_how=None,
    staleness=None,
    tags=None,
    registered_with=None,
    system_type=None,
    filter=None,  # noqa: ARG001
    fields=None,  # noqa: ARG001
    rbac_filter=None,
):
    """
    Get hosts with aggregated application data.

    Returns host information combined with app_data from:
    - Advisor (recommendations, incidents)
    - Vulnerability (CVE counts)
    - Patch (installable advisories)
    - Remediations (remediation plans)
    - Compliance (policies, last scan)
    - Malware (detection status)
    - Image Builder (image info)
    """
    total = 0
    host_list = ()

    try:
        host_list, total, additional_fields, system_profile_fields = get_host_list_from_db(
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
            tags=tags,
            page=page,
            per_page=per_page,
            param_order_by=order_by,
            param_order_how=order_how,
            staleness=staleness,
            registered_with=registered_with,
            system_type=system_type,
            filter=None,
            fields=None,
            rbac_filter=rbac_filter,
        )
    except ValueError as e:
        log_get_host_list_failed(logger)
        flask.abort(400, str(e))

    json_data = _build_host_view_response(total, page, per_page, host_list)

    return flask_json_response(json_data)

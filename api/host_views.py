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
from app.models.database import db
from app.models.host_app_data import get_app_data_models
from app.serialization import serialize_host
from lib.middleware import access

logger = get_logger(__name__)


def _parse_sparse_fields(fields: dict | None) -> dict[str, list[str] | None]:
    """
    Parse sparse fields parameter into {app_name: [fields] or None for all}.
    Returns all apps if fields is omitted or contains only invalid apps.

    Per JSON:API spec (https://jsonapi.org/format/#fetching-sparse-fieldsets):
    - fields[app]=field1,field2 → return only those fields
    - fields[app]=true → return all fields for that app
    - fields[app]= (empty) → return no fields (empty object)

    Meta-key:
    - fields[app_data]=true → return all apps with all fields (explicit shorthand)
    """
    available_apps = get_app_data_models()

    if not fields:
        return {app_name: None for app_name in available_apps.keys()}

    # Handle meta-key: fields[app_data]=true means "return all apps with all fields"
    # This is handled explicitly to avoid accidental behavior if an "app_data" model is ever added
    if "app_data" in fields:
        return {app_name: None for app_name in available_apps.keys()}

    result: dict[str, list[str] | None] = {}

    for app_name, value in fields.items():
        if app_name not in available_apps:
            continue
        # value is a dict like {"field1": True, "field2": True} from custom_fields_parser
        if isinstance(value, dict):
            field_names = [k for k in value.keys() if k]
            # fields[app]=true means all fields
            if field_names == ["true"]:
                result[app_name] = None
            else:
                # Empty list means no fields (per JSON:API spec)
                result[app_name] = field_names

    return result if result else {app_name: None for app_name in available_apps.keys()}


def _filter_app_data_fields(app_data: dict, requested_fields: list[str] | None) -> dict:
    """Filter app data to only include requested fields (None means all, empty list means none)."""
    if requested_fields is None:
        return app_data
    if not requested_fields:
        return {}
    return {k: v for k, v in app_data.items() if k in requested_fields}


def _fetch_app_data_for_hosts(host_ids: list, org_id: str, fields: dict | None = None) -> dict:
    """Fetch app data for hosts. Returns all apps by default if fields is omitted."""
    if not host_ids:
        return {}

    result: dict[str, dict] = {str(host_id): {} for host_id in host_ids}
    parsed_fields = _parse_sparse_fields(fields)
    all_models = get_app_data_models()

    for app_name, requested_app_fields in parsed_fields.items():
        model = all_models[app_name]
        rows = db.session.query(model).filter(model.org_id == org_id, model.host_id.in_(host_ids)).all()

        for row in rows:
            serialized = row.serialize()
            filtered_data = _filter_app_data_fields(serialized, requested_app_fields)
            result[str(row.host_id)][app_name] = filtered_data

    return result


def _build_host_view_response(total, page, per_page, host_list, fields=None):
    """Build the response for the hosts-view endpoint."""
    timestamps = staleness_timestamps()
    identity = get_current_identity()
    staleness = get_staleness_obj(identity.org_id)

    host_ids = [host.id for host in host_list]
    app_data_map = _fetch_app_data_for_hosts(host_ids, identity.org_id, fields)

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
    fields=None,
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

    The `fields` parameter controls which application data is included:
    - No fields parameter → all applications included (default)
    - fields[advisor]=true → only advisor data (all fields)
    - fields[advisor]=recommendations,incidents → specific fields only
    - fields[advisor]= (empty) → no fields for that app (per JSON:API spec)
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
            group_id=None,
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

    json_data = _build_host_view_response(total, page, per_page, host_list, fields)

    return flask_json_response(json_data)

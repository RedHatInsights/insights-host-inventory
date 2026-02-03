from __future__ import annotations

import re
from collections.abc import Iterator
from copy import deepcopy
from itertools import islice
from typing import Any

from sqlalchemy import Boolean
from sqlalchemy import Integer
from sqlalchemy import and_
from sqlalchemy import case
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.exc import MultipleResultsFound
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Query
from sqlalchemy.orm import joinedload
from sqlalchemy.orm import load_only
from sqlalchemy.sql import expression
from sqlalchemy.sql.expression import ColumnElement

from api.filtering.app_data_sorting import resolve_app_sort
from api.filtering.db_filters import ORDER_BY_STATIC_PROFILE_FIELDS
from api.filtering.db_filters import host_id_list_filter
from api.filtering.db_filters import hosts_field_filter
from api.filtering.db_filters import query_filters
from api.filtering.db_filters import rbac_permissions_filter
from api.filtering.db_filters import update_query_for_owner_id
from api.host_query import staleness_timestamps
from api.staleness_query import get_staleness_obj
from app.auth import get_current_identity
from app.auth.identity import Identity
from app.config import ALL_STALENESS_STATES
from app.exceptions import InventoryException
from app.instrumentation import log_get_host_list_succeeded
from app.logging import get_logger
from app.models import Group
from app.models import Host
from app.models import HostDynamicSystemProfile
from app.models import HostGroupAssoc
from app.models import db
from app.models.constants import WORKLOADS_FIELDS
from app.models.system_profile_static import HostStaticSystemProfile
from app.models.system_profile_transformer import DYNAMIC_FIELDS
from app.models.system_profile_transformer import STATIC_FIELDS
from app.serialization import _add_workloads_backward_compatibility
from app.serialization import serialize_host_for_export_svc
from lib.feature_flags import FLAG_INVENTORY_WORKLOADS_FIELDS_BACKWARD_COMPATIBILITY
from lib.feature_flags import get_flag_value

__all__ = (
    "get_all_hosts",
    "get_host_list",
    "get_host_list_by_id_list",
    "get_host_list_for_views",
    "get_host_id_by_insights_id",
    "get_host_tags_list_by_id_list",
    "params_to_order_by",
)

logger = get_logger(__name__)

DEFAULT_COLUMNS = [
    Host.id,
    Host.account,
    Host.org_id,
    Host.insights_id,
    Host.subscription_manager_id,
    Host.satellite_id,
    Host.bios_uuid,
    Host.ip_addresses,
    Host.fqdn,
    Host.mac_addresses,
    Host.provider_id,
    Host.provider_type,
    Host.display_name,
    Host.ansible_host,
    Host.facts,
    Host.reporter,
    Host.per_reporter_staleness,
    Host.stale_timestamp,
    Host.created_on,
    Host.modified_on,
    Host.groups,
    Host.host_type,
    Host.last_check_in,
    Host.openshift_cluster_id,
]


def get_all_hosts() -> list:
    query_results = _find_hosts_entities_query(columns=[Host.id]).all()
    ids_list = [str(result[0]) for result in query_results]

    log_get_host_list_succeeded(logger, ids_list)
    return ids_list


def _get_host_list_using_filters(
    query_base,
    all_filters: list,
    page: int,
    per_page: int,
    param_order_by: str | None,
    param_order_how: str | None,
    fields: dict | None,
    allow_app_fields: bool = False,
) -> tuple[list[Host], int, tuple[str, ...], list[str]]:
    """
    Internal function to get filtered, ordered, and paginated host list.

    Args:
        query_base: Base SQLAlchemy query
        all_filters: List of filter conditions to apply
        page: Page number for pagination
        per_page: Number of results per page
        param_order_by: Field to order by
        param_order_how: Order direction ("ASC" or "DESC")
        fields: Requested fields dict (for system_profile handling)
        allow_app_fields: If True, supports app:field sorting (e.g., "vulnerability:critical_cves")

    Returns:
        Tuple of (items, count, additional_fields, system_profile_fields)
    """
    # Check if 'system_profile' is requested to decide between "Full ORM" vs "Light Columns"
    sp_fields_map = fields.get("system_profile", {}) if fields else {}
    is_sp_requested = bool(sp_fields_map)

    additional_fields = ("system_profile",) if is_sp_requested else ()
    system_profile_fields = list(sp_fields_map.keys()) if is_sp_requested else []

    if is_sp_requested:
        # Load full ORM objects (needed for relationships)
        base_query = _find_hosts_entities_query(query=query_base, columns=None, order_by=param_order_by)

        # Conditionally join related tables based on requested fields
        requested_keys = set(sp_fields_map.keys())

        if requested_keys & set(STATIC_FIELDS) or param_order_by in ORDER_BY_STATIC_PROFILE_FIELDS:
            base_query = base_query.options(joinedload(Host.static_system_profile))

        if requested_keys & (set(DYNAMIC_FIELDS) | WORKLOADS_FIELDS):
            base_query = base_query.options(joinedload(Host.dynamic_system_profile))
    else:
        base_query = _find_hosts_entities_query(
            query=query_base, columns=DEFAULT_COLUMNS.copy(), order_by=param_order_by
        )

    filtered_query = base_query.filter(*all_filters)

    # Count distinct host IDs to avoid overcountiung when JOINs are involved
    count_total = filtered_query.with_entities(func.count(Host.id.distinct())).scalar()

    ordered_query = filtered_query.order_by(
        *params_to_order_by(param_order_by, param_order_how, allow_app_fields=allow_app_fields)
    )
    paginated_results = ordered_query.paginate(page=page, per_page=per_page, error_out=True, count=False)

    db.session.close()

    return paginated_results.items, count_total, additional_fields, system_profile_fields


def get_host_list(
    display_name: str | None,
    fqdn: str | None,
    hostname_or_id: str | None,
    insights_id: str | None,
    subscription_manager_id: str | None,
    provider_id: str | None,
    provider_type: str | None,
    updated_start: str | None,
    updated_end: str | None,
    last_check_in_start: str | None,
    last_check_in_end: str | None,
    group_name: list[str] | None,
    group_id: list[str] | None,
    tags: list[str] | None,
    page: int,
    per_page: int,
    param_order_by: str | None,
    param_order_how: str | None,
    staleness: list[str] | None,
    registered_with: list[str] | None,
    system_type: list[str] | None,
    filter: dict | None,
    fields: dict | None,
    rbac_filter: dict | None,
) -> tuple[list[Host], int, tuple[str, ...], list[str]]:
    all_filters, query_base = query_filters(
        fqdn,
        display_name,
        hostname_or_id,
        insights_id,
        subscription_manager_id,
        provider_id,
        provider_type,
        updated_start,
        updated_end,
        last_check_in_start,
        last_check_in_end,
        group_name,
        group_id,
        tags,
        staleness,
        registered_with,
        system_type,
        filter,
        rbac_filter,
        param_order_by,
        get_current_identity(),
    )

    return _get_host_list_using_filters(
        query_base, all_filters, page, per_page, param_order_by, param_order_how, fields
    )


def get_host_list_by_id_list(
    host_id_list: list[str],
    page: int,
    per_page: int,
    param_order_by: str,
    param_order_how: str,
    fields=None,
    rbac_filter=None,
) -> tuple[list[Host], int, tuple[str, ...], list[str]]:
    all_filters = host_id_list_filter(host_id_list)
    all_filters += rbac_permissions_filter(rbac_filter)

    items, total, additional_fields, system_profile_fields = _get_host_list_using_filters(
        None, all_filters, page, per_page, param_order_by, param_order_how, fields
    )

    return items, total, additional_fields, system_profile_fields


def get_host_id_by_insights_id(insights_id: str, rbac_filter=None) -> str | None:
    identity = get_current_identity()
    all_filters = hosts_field_filter("insights_id", insights_id, False) + rbac_permissions_filter(rbac_filter)
    query = _find_hosts_entities_query(columns=[Host.id], identity=identity).filter(*all_filters)

    try:
        found_id = query.with_entities(Host.id).order_by(Host.modified_on.desc()).scalar()
    except MultipleResultsFound as e:
        raise InventoryException(
            status=409,
            detail=f"More than one host was found with the Insights ID '{insights_id}'",
        ) from e

    return str(found_id) if found_id else None


def params_to_order_by(
    order_by: str | None = None, order_how: str | None = None, allow_app_fields: bool = False
) -> tuple:
    """
    Build ORDER BY clause for host queries.

    Args:
        order_by: Field name or app:field format (if allow_app_fields=True)
        order_how: Sort direction ("ASC" or "DESC")
        allow_app_fields: If True, supports app:field format (e.g., "vulnerability:critical_cves")

    Returns:
        Tuple of SQLAlchemy order expressions
    """
    modified_on_ordering = (Host.modified_on.desc(),)
    ordering: tuple = ()

    # Check for app sort fields (only when explicitly enabled)
    if allow_app_fields:
        resolved = resolve_app_sort(order_by)
        if resolved:
            _, column = resolved

            # Validate order_how consistently with standard fields
            if order_how is not None and order_how not in ("ASC", "DESC"):
                raise ValueError('Unsupported ordering direction, use "ASC" or "DESC".')

            # Apply ordering with NULLS LAST (default to ASC if not specified)
            order_expr = column.desc().nullslast() if order_how == "DESC" else column.asc().nullslast()

            # Always add secondary sort for pagination stability
            return (order_expr,) + modified_on_ordering + (Host.id.desc(),)

    if order_by == "updated":
        if order_how:
            modified_on_ordering = (_order_how(Host.modified_on, order_how),)
    elif order_by == "display_name":
        ordering = (_order_how(Host.display_name, order_how),) if order_how else (Host.display_name.asc(),)
    elif order_by == "group_name":
        return _get_group_name_order_post_kessel(order_how)
    elif order_by == "operating_system":
        ordering = (_order_how(Host.operating_system, order_how),) if order_how else (Host.operating_system.desc(),)  # type: ignore [attr-defined]

    elif order_by == "last_check_in":
        ordering = (_order_how(Host.last_check_in, order_how),) if order_how else (Host.last_check_in.desc(),)

    elif order_by:
        raise ValueError(
            'Unsupported ordering column: use "updated", "display_name",'
            ' "group_name", "operating_system" or "last_check_in"'
        )
    elif order_how:
        raise ValueError(
            "Providing ordering direction without a column is not supported."
            " Provide order_by={updated,display_name,group_name,operating_system,last_check_in}."
        )

    return ordering + modified_on_ordering + (Host.id.desc(),)


def _order_how(column, order_how: str):
    if order_how == "ASC":
        return column.asc()
    elif order_how == "DESC":
        return column.desc()
    else:
        raise ValueError('Unsupported ordering direction, use "ASC" or "DESC".')


def get_host_list_for_views(
    display_name: str | None,
    fqdn: str | None,
    hostname_or_id: str | None,
    insights_id: str | None,
    subscription_manager_id: str | None,
    provider_id: str | None,
    provider_type: str | None,
    updated_start: str | None,
    updated_end: str | None,
    last_check_in_start: str | None,
    last_check_in_end: str | None,
    group_name: list[str] | None,
    group_id: list[str] | None,
    tags: list[str] | None,
    page: int,
    per_page: int,
    param_order_by: str | None,
    param_order_how: str | None,
    staleness: list[str] | None,
    registered_with: list[str] | None,
    system_type: list[str] | None,
    filter: dict | None,
    rbac_filter: dict | None,
) -> tuple[list[Host], int]:
    """
    Get host list for views endpoint with unified sorting support.

    Supports both standard host fields and application data sorting.
    Automatically detects app:field format (e.g., "vulnerability:critical_cves")
    and adds the required JOIN when needed.

    Returns:
        Tuple of (host_list, total_count)
    """
    all_filters, query_base = query_filters(
        fqdn,
        display_name,
        hostname_or_id,
        insights_id,
        subscription_manager_id,
        provider_id,
        provider_type,
        updated_start,
        updated_end,
        last_check_in_start,
        last_check_in_end,
        group_name,
        group_id,
        tags,
        staleness,
        registered_with,
        system_type,
        filter,
        rbac_filter,
        param_order_by,
        get_current_identity(),
    )

    # Automatically add LEFT JOIN for app data table if sorting by app field
    resolved = resolve_app_sort(param_order_by)
    if resolved:
        app_sort_model, _ = resolved
        query_base = query_base.outerjoin(
            app_sort_model, and_(Host.org_id == app_sort_model.org_id, Host.id == app_sort_model.host_id)
        )

    # Reuse _get_host_list_using_filters with app fields enabled, no system_profile support
    items, count, _, _ = _get_host_list_using_filters(
        query_base, all_filters, page, per_page, param_order_by, param_order_how, fields=None, allow_app_fields=True
    )
    return items, count


def _find_hosts_entities_query(
    query=None,
    columns: list[ColumnElement] | None = None,
    identity: Any = None,
    order_by: str | None = None,
) -> Query:
    identity = identity or get_current_identity()

    if query is None:
        query = db.session.query(Host).outerjoin(HostGroupAssoc).outerjoin(Group)
        if order_by in ORDER_BY_STATIC_PROFILE_FIELDS:
            query = query.outerjoin(HostStaticSystemProfile)
        query = query.filter(Host.org_id == identity.org_id)

    if columns:
        query = query.with_entities(*columns)
    return update_query_for_owner_id(identity, query)


def _find_hosts_model_query(columns: list[ColumnElement] | None = None, identity: Any = None) -> Query:
    query = db.session.query(Host).outerjoin(HostGroupAssoc).outerjoin(Group)

    # In this case, return a list of Hosts
    # wih the requested columns.
    # When used with scalars,
    # the entire Host object is returned,
    # instead of just the first column,
    # that is the case of _find_hosts_entities_query
    # See: https://docs.sqlalchemy.org/en/20/core/connections.html#sqlalchemy.engine.Result.scalars

    query = query.options(load_only(*columns))
    return update_query_for_owner_id(identity, query)


def get_host_tags_list_by_id_list(
    host_id_list: list[str], limit: int, offset: int, order_by: str, order_how: str, rbac_filter: dict
) -> tuple[dict, int]:
    columns = [Host.id, Host.tags]
    query = _find_hosts_entities_query(columns=columns)
    all_filters = host_id_list_filter(host_id_list)
    all_filters += rbac_permissions_filter(rbac_filter)
    order = params_to_order_by(order_by, order_how)
    query_results = query.filter(*all_filters).order_by(*order).offset(offset).limit(limit).all()
    db.session.close()
    host_tags_dict, _ = _expand_host_tags(query_results)
    return host_tags_dict, len(host_id_list)


def _add_tag_values(host_namespace, tag_key, tag_value, host_id, host_tags, host_tags_tracker) -> tuple[list, dict]:
    converted_value = _convert_null_string(tag_value) if tag_value else ""
    host_tag_str = f"{_convert_null_string(host_namespace)}/{_convert_null_string(tag_key)}={converted_value}"
    host_tag_obj = {
        "namespace": _convert_null_string(host_namespace),
        "key": _convert_null_string(tag_key),
        "value": _convert_null_string(tag_value),
    }
    host_tags.append(host_tag_obj)
    if host_tag_str not in host_tags_tracker:
        host_tags_tracker[host_tag_str] = {"output": host_tag_obj, "hosts": [host_id]}
    else:
        host_tags_tracker[host_tag_str].get("hosts").append(host_id)
    return host_tags, host_tags_tracker


def _expand_host_tags(hosts: list[Host]) -> tuple[dict, dict]:
    host_tags_tracker: dict[str, dict[str, dict[str, str] | list[str]]] = {}
    host_tags_dict: dict[str, list[dict[str, str]]] = {}
    for host in hosts:
        host_tags: list[dict[str, str]] = []
        host_namespace_tags_dict = host.tags
        for host_namespace, host_namespace_tags in host_namespace_tags_dict.items():
            for tag_key, tag_values in host_namespace_tags.items():
                if isinstance(tag_values, list) and tag_values:
                    for tag_value in tag_values:
                        host_tags, host_tags_tracker = _add_tag_values(
                            host_namespace, tag_key, tag_value, host.id, host_tags, host_tags_tracker
                        )
                else:
                    host_tags, host_tags_tracker = _add_tag_values(
                        host_namespace, tag_key, tag_values or None, host.id, host_tags, host_tags_tracker
                    )
        host_tags_dict[host.id] = host_tags
    return host_tags_dict, host_tags_tracker


def _convert_null_string(input: str | list):
    if input == "null" or input == []:
        return None
    return input


def get_tag_list(
    display_name: str | None,
    fqdn: str | None,
    hostname_or_id: str | None,
    insights_id: str | None,
    subscription_manager_id: str | None,
    provider_id: str | None,
    provider_type: str | None,
    updated_start: str | None,
    updated_end: str | None,
    last_check_in_start: str | None,
    last_check_in_end: str | None,
    group_name: list[str] | None,
    group_id: list[str] | None,
    tags: list[str] | None,
    limit: int,
    offset: int,
    order_by: str | None,
    order_how: str | None,
    search: str | None,
    staleness: list[str] | None,
    registered_with: list[str] | None,
    system_type: list[str] | None,
    filter: dict | None,
    rbac_filter: dict | None,
) -> tuple[list, int]:
    if order_by not in ["tag", "count"]:
        raise ValueError('Unsupported ordering column: use "tag" or "count".')
    elif order_how and order_by not in ["tag", "count"]:
        raise ValueError(
            "Providing ordering direction without a column is not supported. Provide order_by={tag,count}."
        )

    columns = [Host.id, Host.tags]
    all_filters, query_base = query_filters(
        fqdn,
        display_name,
        hostname_or_id,
        insights_id,
        subscription_manager_id,
        provider_id,
        provider_type,
        updated_start,
        updated_end,
        last_check_in_start,
        last_check_in_end,
        group_name,
        group_id,
        tags,
        staleness,
        registered_with,
        system_type,
        filter,
        rbac_filter,
        order_by,
        get_current_identity(),
    )
    query = _find_hosts_entities_query(query=query_base, columns=columns)

    query_results = query.filter(*all_filters).all()
    db.session.close()
    _, host_tags_dict = _expand_host_tags(query_results)
    host_tags = host_tags_dict
    if search:
        regex = re.compile(search, re.IGNORECASE)
        host_tags = {}
        for key in host_tags_dict.keys():
            if regex.search(key):
                host_tags[key] = host_tags_dict[key]

    tag_list = []
    query_count = 0
    tag_count_list = []
    for stored_key, tag_contents in host_tags.items():
        tag_count_item = {"tag": stored_key, "count": len(tag_contents.get("hosts"))}
        tag_count_list.append(tag_count_item)
    if order_by == "tag":
        sorted_tag_count_list = sorted(tag_count_list, reverse=order_how == "DESC", key=lambda item: item["tag"])
    if order_by == "count":
        sorted_tag_count_list = sorted(tag_count_list, reverse=order_how == "DESC", key=lambda item: item["count"])
    for tag_item in sorted_tag_count_list:
        tag_key = tag_item.get("tag")
        tag_dict = host_tags[tag_key]
        output = {"tag": tag_dict.get("output", {}), "count": len(tag_dict.get("hosts", []))}
        tag_list.append(output)

    query_count = len(tag_list)
    tag_list = list(islice(islice(tag_list, offset, None), limit))
    return tag_list, query_count


def get_os_info(
    limit: int,
    offset: int,
    staleness: list[str] | None,
    tags: list[str],
    registered_with: list[str] | None,
    filter: dict,
    rbac_filter: dict,
    identity: Identity,
):
    os_field = HostStaticSystemProfile.operating_system

    columns = [
        os_field["name"].astext.label("name"),
        os_field["major"].astext.cast(Integer).label("major"),
        os_field["minor"].astext.cast(Integer).label("minor"),
        func.count().label("count"),
    ]

    filters, query_base = query_filters(
        tags=tags,
        staleness=staleness,
        registered_with=registered_with,
        filter=filter,
        rbac_filter=rbac_filter,
        identity=identity,
        join_static_profile=True,
    )
    os_query = _find_hosts_entities_query(query=query_base, columns=columns, identity=identity)

    # Only include records that have set an operating_system.name
    filters += (columns[0].isnot(None),)

    query_results = os_query.filter(*filters).group_by(*columns[:-1]).order_by(func.count().desc()).all()
    db.session.close()

    os_count_list = []
    for result in query_results:
        os_count_item = {
            "value": {"name": result[0], "major": int(result[1]), "minor": int(result[2])},
            "count": result[3],
        }
        os_count_list.append(os_count_item)

    query_count = len(os_count_list)
    os_list = list(islice(islice(os_count_list, offset, None), limit))
    return os_list, query_count


def get_sap_system_info(
    page: int,
    per_page: int,
    staleness: list[str],
    tags: list[str],
    registered_with: list[str],
    filter: dict,
    rbac_filter: dict,
    identity: Identity,
):
    # Use the new system_profiles_dynamic table for SAP data
    dynamic_sap_system = HostDynamicSystemProfile.workloads["sap"]["sap_system"]

    columns = [
        dynamic_sap_system.label("value"),
    ]

    # Request dynamic profile join since we need workloads data
    # query_filters will automatically add the join
    filters, query_base = query_filters(
        tags=tags,
        staleness=staleness,
        registered_with=registered_with,
        filter=filter,
        rbac_filter=rbac_filter,
        identity=identity,
        join_dynamic_profile=True,  # Explicitly request HostDynamicSystemProfile join
    )

    sap_query = _find_hosts_entities_query(query=query_base, columns=columns)

    # Filter for existing SAP system data
    sap_filter = [
        func.jsonb_typeof(dynamic_sap_system) == "boolean",
        dynamic_sap_system.astext.cast(Boolean) != None,  # noqa:E711
    ]

    sap_query = sap_query.filter(*filters).filter(*sap_filter)

    subquery = sap_query.subquery()
    agg_query = db.session.query(subquery, func.count()).group_by("value")
    query_results = agg_query.paginate(page=page, per_page=per_page, error_out=True)
    db.session.close()
    result = [{"value": qr[0], "count": qr[1]} for qr in query_results.items]
    return result, query_results.total


def get_sap_sids_info(
    limit: int,
    offset: int,
    staleness: list[str],
    tags: list[str],
    registered_with: list[str],
    filter: dict,
    rbac_filter: dict,
    search: str,
    identity: Identity,
):
    # Use the new system_profiles_dynamic table for SAP SIDS data
    dynamic_sap_sids = HostDynamicSystemProfile.workloads["sap"]["sids"]

    columns = [
        Host.id,
        func.jsonb_array_elements_text(dynamic_sap_sids).label("sap_sids"),
    ]

    # Request dynamic profile join since we need workloads data
    # query_filters will automatically add the join
    filters, query_base = query_filters(
        tags=tags,
        staleness=staleness,
        registered_with=registered_with,
        filter=filter,
        rbac_filter=rbac_filter,
        identity=identity,
        join_dynamic_profile=True,  # Explicitly request HostDynamicSystemProfile join
    )

    sap_sids_query = _find_hosts_entities_query(query_base, columns)

    query_results = sap_sids_query.filter(*filters).all()
    db.session.close()
    sap_sids = {}
    for result in query_results:
        host_id = result[0]
        sap_sid = result[1]
        if sap_sid not in sap_sids:
            sap_sids[sap_sid] = {host_id}
        else:
            sap_sids[sap_sid].add(host_id)

    sap_sids_dict = sap_sids
    if search:
        regex = re.compile(search, re.IGNORECASE)
        sap_sids_dict = {}
        for key in sap_sids.keys():
            if regex.search(key):
                sap_sids_dict[key] = sap_sids[key]

    sap_sids_list = []
    query_count = 0
    sap_sids_count_list = []
    for sap_sid, host_list in sap_sids_dict.items():
        sap_sid_count_item = {"value": sap_sid, "count": len(host_list)}
        sap_sids_count_list.append(sap_sid_count_item)
    sap_sids_count_list = sorted(sap_sids_count_list, reverse=True, key=lambda item: item["count"])
    query_count = len(sap_sids_count_list)
    sap_sids_list = list(islice(islice(sap_sids_count_list, offset, None), limit))
    return sap_sids_list, query_count


def get_sparse_system_profile(
    host_id_list: list[str],
    page: int,
    per_page: int,
    param_order_by: str,
    param_order_how: str,
    fields: dict[str, list[str]],
    rbac_filter: dict,
) -> tuple[int, list[dict[str, str | dict]]]:
    # Define legacy workload fields that may need backward compatibility
    # Note: rhel_ai is NOT included because its legacy structure differs from workloads.rhel_ai
    legacy_workload_fields = {
        "sap",
        "sap_system",
        "sap_sids",
        "sap_instance_number",
        "sap_version",
        "ansible",
        "intersystems",
        "mssql",
        "third_party_services",
    }

    # Track if we need to fetch workloads for backward compatibility
    requested_sp_fields_dict: dict[str, bool] = fields.get("system_profile", {}) if fields else {}  # type: ignore[assignment]
    requested_sp_fields = list(requested_sp_fields_dict.keys()) if isinstance(requested_sp_fields_dict, dict) else []
    workloads_requested = "workloads" in requested_sp_fields
    workloads_needed_for_compat = (
        get_flag_value(FLAG_INVENTORY_WORKLOADS_FIELDS_BACKWARD_COMPATIBILITY)
        and requested_sp_fields
        and any(field in legacy_workload_fields for field in requested_sp_fields)
    )

    needs_static_join = False
    needs_dynamic_join = False

    if fields and fields.get("system_profile"):
        # If backward compatibility is enabled and legacy fields are requested,
        # also fetch workloads field so we can populate legacy fields from it
        fields_to_fetch = deepcopy(requested_sp_fields)
        if workloads_needed_for_compat and not workloads_requested:
            fields_to_fetch.append("workloads")

        jsonb_parts = []
        for key in fields_to_fetch:
            if key in STATIC_FIELDS:
                jsonb_parts.extend([key, getattr(HostStaticSystemProfile, key)])
                needs_static_join = True
            elif key in DYNAMIC_FIELDS:
                jsonb_parts.extend([key, getattr(HostDynamicSystemProfile, key)])
                needs_dynamic_join = True

        columns = [
            Host.id,
            func.jsonb_strip_nulls(func.jsonb_build_object(*jsonb_parts))
            if jsonb_parts
            else func.jsonb_build_object(),
        ]
    else:
        # Fetch all fields from both normalized tables
        # Build separate JSONB objects for static and dynamic fields to avoid exceeding
        # PostgreSQL's 100-argument limit for jsonb_build_object
        static_parts = [field for f in STATIC_FIELDS for field in (f, getattr(HostStaticSystemProfile, f))]
        dynamic_parts = [field for f in DYNAMIC_FIELDS for field in (f, getattr(HostDynamicSystemProfile, f))]
        # Merge the two JSONB objects using || operator
        static_jsonb = func.jsonb_build_object(*static_parts)
        dynamic_jsonb = func.jsonb_build_object(*dynamic_parts)
        merged_jsonb = static_jsonb.op("||")(dynamic_jsonb)
        columns = [
            Host.id,
            func.jsonb_strip_nulls(merged_jsonb),
        ]
        # When fetching all fields, we need both joins
        needs_static_join = True
        needs_dynamic_join = True

    all_filters = host_id_list_filter(host_id_list) + rbac_permissions_filter(rbac_filter)

    identity = get_current_identity()
    query_base = (
        db.session.query(Host).outerjoin(HostGroupAssoc).outerjoin(Group).filter(Host.org_id == identity.org_id)
    )
    if needs_static_join:
        query_base = query_base.outerjoin(HostStaticSystemProfile)
    if needs_dynamic_join:
        query_base = query_base.outerjoin(HostDynamicSystemProfile)

    base_query = _find_hosts_entities_query(query=query_base, columns=columns, identity=identity)

    sp_query = base_query.filter(*all_filters).order_by(*params_to_order_by(param_order_by, param_order_how))

    query_results = sp_query.paginate(page=page, per_page=per_page, error_out=True)
    db.session.close()

    # Build the result list
    result_list = [{"id": str(item[0]), "system_profile": item[1]} for item in query_results.items]

    # Apply backward compatibility logic if the flag is enabled
    if get_flag_value(FLAG_INVENTORY_WORKLOADS_FIELDS_BACKWARD_COMPATIBILITY):
        for host_data in result_list:
            if host_data["system_profile"]:
                # Apply backward compatibility to populate legacy fields from workloads.*
                host_data["system_profile"] = _add_workloads_backward_compatibility(host_data["system_profile"])

                # If specific fields were requested, filter the response
                if requested_sp_fields:
                    # Remove workloads if it was only fetched for backward compatibility
                    if workloads_needed_for_compat and not workloads_requested:
                        host_data["system_profile"].pop("workloads", None)

                    # Remove legacy fields that weren't explicitly requested
                    for field in legacy_workload_fields:
                        if field in host_data["system_profile"] and field not in requested_sp_fields:
                            del host_data["system_profile"][field]

    return query_results.total, result_list


def get_host_ids_list(
    display_name: str | None,
    fqdn: str | None,
    hostname_or_id: str | None,
    insights_id: str | None,
    subscription_manager_id: str | None,
    provider_id: str | None,
    provider_type: str | None,
    updated_start: str | None,
    updated_end: str | None,
    last_check_in_start: str | None,
    last_check_in_end: str | None,
    group_name: list[str] | None,
    group_id: list[str] | None,
    registered_with: list[str] | None,
    system_type: list[str] | None,
    staleness: list[str] | None,
    tags: list[str] | None,
    filter: dict | None,
    rbac_filter: dict | None,
    identity: Identity,
) -> list[str]:
    all_filters, base_query = query_filters(
        fqdn,
        display_name,
        hostname_or_id,
        insights_id,
        subscription_manager_id,
        provider_id,
        provider_type,
        updated_start,
        updated_end,
        last_check_in_start,
        last_check_in_end,
        group_name,
        group_id,
        tags,
        staleness,
        registered_with,
        system_type,
        filter,
        rbac_filter,
        identity=identity,
    )
    host_list = [str(res[0]) for res in _find_hosts_entities_query(base_query, [Host.id]).filter(*all_filters).all()]
    db.session.close()
    return host_list


def get_hosts_to_export(
    identity: Identity,
    filters: dict | None = None,
    rbac_filter: dict | None = None,
    batch_size: int = 0,
) -> Iterator[dict]:
    if filters is None:
        filters = {}
    if rbac_filter is None:
        rbac_filter = {}

    st_timestamps = staleness_timestamps()
    staleness = get_staleness_obj(identity.org_id)

    q_filters, _ = query_filters(
        filter=filters, rbac_filter=rbac_filter, staleness=ALL_STALENESS_STATES, identity=identity
    )
    columns = [
        Host.id,
        Host.account,
        Host.org_id,
        Host.display_name,
        Host.host_type,
        Host.modified_on,
        Host.facts,
        Host.reporter,
        Host.created_on,
        Host.groups,
    ]

    export_host_query = (
        _find_hosts_model_query(identity=identity, columns=columns)
        .options(joinedload(Host.static_system_profile), joinedload(Host.dynamic_system_profile))
        .filter(*q_filters)
    )
    export_host_query = export_host_query.execution_options(yield_per=batch_size)

    try:
        num_hosts_query = select(func.count()).select_from(export_host_query.subquery())
        num_hosts = db.session.scalar(num_hosts_query)
        logger.debug(f"Number of hosts to be exported: {num_hosts}")

        for host in db.session.scalars(export_host_query):
            yield serialize_host_for_export_svc(host, staleness_timestamps=st_timestamps, staleness=staleness)

    except SQLAlchemyError as e:  # Most likely ObjectDeletedError, but catching all DB errors
        raise InventoryException(title="DB Error", detail=str(e)) from e

    db.session.close()


def _get_group_name_order_post_kessel(order_how):
    host_group = Host.groups[0]  # groups is a list with one dict at this point
    high_prio, low_prio = 0, 1

    # Order by group_name
    base_ordering = host_group["name"].asc() if order_how in ("ASC", None) else host_group["name"].desc()

    # Override default sorting
    # When sorting by group_name ASC, ungrouped hosts should show first
    ungrouped_expr = host_group["ungrouped"].as_boolean()
    ungrouped_order = (
        case((ungrouped_expr == expression.true(), high_prio), else_=low_prio)
        if order_how in ("ASC", None)
        else case((ungrouped_expr == expression.true(), low_prio), else_=high_prio)
    )

    return ungrouped_order, base_ordering, Host.modified_on.desc(), Host.id.desc()

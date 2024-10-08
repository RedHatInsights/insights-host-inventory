import re
from itertools import islice
from typing import Iterator
from typing import List
from typing import Tuple

from sqlalchemy import Boolean
from sqlalchemy import func
from sqlalchemy import String
from sqlalchemy.exc import MultipleResultsFound
from sqlalchemy.orm import load_only
from sqlalchemy.orm import Query
from sqlalchemy.sql.expression import cast
from sqlalchemy.sql.expression import ColumnElement

from api.filtering.db_filters import canonical_fact_filter
from api.filtering.db_filters import host_id_list_filter
from api.filtering.db_filters import query_filters
from api.filtering.db_filters import rbac_permissions_filter
from api.host_query import staleness_timestamps
from api.staleness_query import get_staleness_obj
from app import db
from app.auth import get_current_identity
from app.exceptions import InventoryException
from app.instrumentation import log_get_host_list_succeeded
from app.logging import get_logger
from app.models import Group
from app.models import Host
from app.models import HostGroupAssoc
from app.serialization import serialize_host_for_export_svc
from lib.host_repository import ALL_STALENESS_STATES
from lib.host_repository import update_query_for_owner_id


__all__ = (
    "get_all_hosts",
    "get_host_list",
    "get_host_list_by_id_list",
    "get_host_id_by_insights_id",
    "get_host_tags_list_by_id_list",
    "params_to_order_by",
)

logger = get_logger(__name__)

DEFAULT_COLUMNS = [
    Host.canonical_facts,
    Host.id,
    Host.account,
    Host.org_id,
    Host.display_name,
    Host.ansible_host,
    Host.facts,
    Host.reporter,
    Host.per_reporter_staleness,
    Host.stale_timestamp,
    Host.created_on,
    Host.modified_on,
    Host.groups,
    Host.system_profile_facts["host_type"].label("host_type"),
]


def get_all_hosts() -> List:
    query_results = _find_hosts_entities_query(columns=[Host.id]).all()
    ids_list = [str(result[0]) for result in query_results]

    log_get_host_list_succeeded(logger, ids_list)
    return ids_list


def _get_host_list_using_filters(
    query_base,
    all_filters: List,
    page: int,
    per_page: int,
    param_order_by: str,
    param_order_how: str,
    fields: List[str],
) -> Tuple[List[Host], int, Tuple[str], List[str]]:
    columns = DEFAULT_COLUMNS
    system_profile_fields = ["host_type"]
    if fields and fields.get("system_profile"):
        additional_fields = ("system_profile",)
        system_profile_fields += list(fields.get("system_profile").keys())
        columns = list(DEFAULT_COLUMNS)
        columns.append(Host.system_profile_facts)
    else:
        additional_fields = tuple()

    base_query = _find_hosts_entities_query(query_base=query_base, columns=columns).filter(*all_filters)
    host_query = base_query.order_by(*params_to_order_by(param_order_by, param_order_how))

    # Count separately because the COUNT done by .paginate() is inefficient
    count_total = base_query.with_entities(func.count()).scalar()

    query_results = host_query.paginate(page=page, per_page=per_page, error_out=True, count=False)
    db.session.close()

    return query_results.items, count_total, additional_fields, system_profile_fields


def get_host_list(
    display_name: str,
    fqdn: str,
    hostname_or_id: str,
    insights_id: str,
    provider_id: str,
    provider_type: str,
    updated_start: str,
    updated_end: str,
    group_name: str,
    tags: List[str],
    page: int,
    per_page: int,
    param_order_by: str,
    param_order_how: str,
    staleness: List[str],
    registered_with: List[str],
    filter: dict,
    fields: List[str],
    rbac_filter: dict,
) -> Tuple[List[Host], int, Tuple[str], List[str]]:
    all_filters, query_base = query_filters(
        fqdn,
        display_name,
        hostname_or_id,
        insights_id,
        provider_id,
        provider_type,
        updated_start,
        updated_end,
        group_name,
        None,
        tags,
        staleness,
        registered_with,
        filter,
        rbac_filter,
        param_order_by,
    )

    return _get_host_list_using_filters(
        query_base, all_filters, page, per_page, param_order_by, param_order_how, fields
    )


def get_host_list_by_id_list(
    host_id_list: List[str],
    page: int,
    per_page: int,
    param_order_by: str,
    param_order_how: str,
    fields=None,
    rbac_filter=None,
) -> Tuple[List[Host], int, Tuple[str], List[str]]:
    all_filters = host_id_list_filter(host_id_list)
    all_filters += rbac_permissions_filter(rbac_filter)

    items, total, additional_fields, system_profile_fields = _get_host_list_using_filters(
        None, all_filters, page, per_page, param_order_by, param_order_how, fields
    )

    return items, total, additional_fields, system_profile_fields


def get_host_id_by_insights_id(insights_id: str, rbac_filter=None) -> str:
    identity = get_current_identity()
    all_filters = canonical_fact_filter("insights_id", insights_id) + rbac_permissions_filter(rbac_filter)
    query = _find_hosts_entities_query(columns=[Host.id], identity=identity).filter(*all_filters)

    try:
        found_id = query.with_entities(Host.id).order_by(Host.modified_on.desc()).scalar()
    except MultipleResultsFound:
        raise InventoryException(
            status=409,
            detail=f"More than one host was found with the Insights ID '{insights_id}'",
        )

    return str(found_id) if found_id else None


def params_to_order_by(order_by: str = None, order_how: str = None) -> Tuple:
    modified_on_ordering = (Host.modified_on.desc(),)
    ordering = ()

    if order_by == "updated":
        if order_how:
            modified_on_ordering = (_order_how(Host.modified_on, order_how),)
    elif order_by == "display_name":
        if order_how:
            ordering = (_order_how(Host.display_name, order_how),)
        else:
            ordering = (Host.display_name.asc(),)
    elif order_by == "group_name":
        if order_how:
            base_ordering = _order_how(Group.name, order_how)
        else:
            base_ordering = Group.name.asc()

        # Override default sorting
        # When sorting by group_name ASC, ungrouped hosts should show first
        if order_how == "DESC":
            ordering = (base_ordering.nulls_last(),)
        else:
            ordering = (base_ordering.nulls_first(),)
    elif order_by == "operating_system":
        if order_how:
            ordering = (_order_how(Host.operating_system, order_how),)
        else:
            ordering = (Host.operating_system.desc(),)
    elif order_by:
        raise ValueError(
            'Unsupported ordering column: use "updated", "display_name", "group_name", or "operating_system".'
        )
    elif order_how:
        raise ValueError(
            "Providing ordering direction without a column is not supported. "
            "Provide order_by={updated,display_name}."
        )

    return ordering + modified_on_ordering + (Host.id.desc(),)


def _order_how(column, order_how: str):
    if order_how == "ASC":
        return column.asc()
    elif order_how == "DESC":
        return column.desc()
    else:
        raise ValueError('Unsupported ordering direction, use "ASC" or "DESC".')


def _find_hosts_entities_query(query_base=None, columns: List[ColumnElement] = None, identity: object = None) -> Query:
    if query_base is None:
        query_base = db.session.query(Host).join(HostGroupAssoc, isouter=True).join(Group, isouter=True)

    if not identity:
        identity = get_current_identity()

    query = query_base.filter(Host.org_id == identity.org_id)
    if columns:
        query = query.with_entities(*columns)
    return update_query_for_owner_id(identity, query)


def _find_hosts_model_query(columns: List[ColumnElement] = None, identity: object = None) -> Query:
    query_base = db.session.query(Host).join(HostGroupAssoc, isouter=True).join(Group, isouter=True)
    query = query_base.filter(Host.org_id == identity.org_id)

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
    host_id_list: List[str], limit: int, offset: int, order_by: str, order_how: str, rbac_filter: dict
) -> Tuple[dict, int]:
    columns = [Host.id, Host.tags]
    query = _find_hosts_entities_query(columns=columns)
    all_filters = host_id_list_filter(host_id_list=host_id_list)
    all_filters += rbac_permissions_filter(rbac_filter)
    order = params_to_order_by(order_by, order_how)
    query_results = query.filter(*all_filters).order_by(*order).offset(offset).limit(limit).all()
    db.session.close()
    host_tags_dict, _ = _expand_host_tags(query_results)
    return host_tags_dict, len(host_id_list)


def _add_tag_values(host_namespace, tag_key, tag_value, host_id, host_tags, host_tags_tracker) -> Tuple[dict, dict]:
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


def _expand_host_tags(hosts: List[Host]) -> Tuple[dict, dict]:
    host_tags_tracker = {}
    host_tags_dict = {}
    for host in hosts:
        host_tags = []
        host_namespace_tags_dict = host.tags
        for host_namespace, host_namespace_tags in host_namespace_tags_dict.items():
            for tag_key, tag_values in host_namespace_tags.items():
                if isinstance(tag_values, List) and tag_values:
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


def _convert_null_string(input: str):
    if input == "null" or input == []:
        return None
    return input


def get_tag_list(
    display_name: str,
    fqdn: str,
    hostname_or_id: str,
    insights_id: str,
    provider_id: str,
    provider_type: str,
    updated_start: str,
    updated_end: str,
    group_name: str,
    tags: List[str],
    limit: int,
    offset: int,
    order_by: str,
    order_how: str,
    search: str,
    staleness: List[str],
    registered_with: List[str],
    filter: dict,
    rbac_filter: dict,
) -> Tuple[dict, int]:
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
        provider_id,
        provider_type,
        updated_start,
        updated_end,
        group_name,
        None,
        tags,
        staleness,
        registered_with,
        filter,
        rbac_filter,
        order_by,
    )
    query = _find_hosts_entities_query(query_base=query_base, columns=columns)

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
    staleness: List[str],
    tags: List[str],
    registered_with: List[str],
    filter: dict,
    rbac_filter: dict,
):
    columns = [
        Host.system_profile_facts["operating_system"]["name"].label("name"),
        cast(Host.system_profile_facts["operating_system"]["major"], String).label("major"),
        cast(Host.system_profile_facts["operating_system"]["minor"], String).label("minor"),
    ]

    filters, query_base = query_filters(
        tags=tags, staleness=staleness, registered_with=registered_with, filter=filter, rbac_filter=rbac_filter
    )
    os_query = _find_hosts_entities_query(query_base=query_base, columns=columns)

    # Only include records that have set an operating_system.name
    filters += (columns[0].isnot(None),)

    query_results = os_query.filter(*filters).all()
    db.session.close()
    os_dict = {}
    for result in query_results:
        if not result or None in result:
            continue
        operating_system = ".".join(result)
        if operating_system not in os_dict:
            os_dict[operating_system] = 1
        else:
            os_dict[operating_system] += 1

    os_count_list = []
    for os_joined, count in os_dict.items():
        os = os_joined.split(".")
        os_count_item = {"value": {"name": os[0], "major": int(os[1]), "minor": int(os[2])}, "count": count}
        os_count_list.append(os_count_item)

    os_count_list = sorted(os_count_list, reverse=True, key=lambda item: item["count"])
    query_count = len(os_count_list)
    os_list = list(islice(islice(os_count_list, offset, None), limit))
    return os_list, query_count


def get_sap_system_info(
    page: int,
    per_page: int,
    staleness: List[str],
    tags: List[str],
    registered_with: List[str],
    filter: dict,
    rbac_filter: dict,
):
    columns = [
        Host.system_profile_facts["sap_system"].label("value"),
    ]

    filters, query_base = query_filters(
        tags=tags, staleness=staleness, registered_with=registered_with, filter=filter, rbac_filter=rbac_filter
    )
    sap_query = _find_hosts_entities_query(query_base=query_base, columns=columns)
    sap_filter = [
        func.jsonb_typeof(Host.system_profile_facts["sap_system"]) == "boolean",
        Host.system_profile_facts["sap_system"].astext.cast(Boolean) != None,  # noqa:E711
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
    staleness: List[str],
    tags: List[str],
    registered_with: List[str],
    filter: dict,
    rbac_filter: dict,
    search: str,
):
    columns = [
        Host.id,
        func.jsonb_array_elements_text(Host.system_profile_facts["sap_sids"]).label("sap_sids"),
    ]
    filters, query_base = query_filters(
        tags=tags, staleness=staleness, registered_with=registered_with, filter=filter, rbac_filter=rbac_filter
    )
    sap_sids_query = _find_hosts_entities_query(query_base=query_base, columns=columns)
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
    host_id_list: List[str],
    page: int,
    per_page: int,
    param_order_by: str,
    param_order_how: str,
    fields: List[str],
    rbac_filter: dict,
) -> Tuple[List[Host], int]:
    if fields and fields.get("system_profile"):
        columns = [
            Host.id,
            func.jsonb_strip_nulls(
                func.jsonb_build_object(
                    *[
                        kv
                        for key in fields.get("system_profile")
                        for kv in (key, Host.system_profile_facts[key].label(key))
                    ]
                ).label("system_profile_facts")
            ),
        ]
    else:
        columns = [Host.id, Host.system_profile_facts]

    all_filters = host_id_list_filter(host_id_list) + rbac_permissions_filter(rbac_filter)
    sp_query = (
        _find_hosts_entities_query(columns=columns)
        .filter(*all_filters)
        .order_by(*params_to_order_by(param_order_by, param_order_how))
    )

    query_results = sp_query.paginate(page=page, per_page=per_page, error_out=True)
    db.session.close()

    return query_results.total, [{"id": str(item[0]), "system_profile": item[1]} for item in query_results.items]


def get_host_ids_list(
    display_name: str,
    fqdn: str,
    hostname_or_id: str,
    insights_id: str,
    provider_id: str,
    provider_type: str,
    updated_start: str,
    updated_end: str,
    group_name: str,
    registered_with: List[str],
    staleness: List[str],
    tags: List[str],
    filter: dict,
    rbac_filter: dict,
) -> List[str]:
    all_filters, base_query = query_filters(
        fqdn,
        display_name,
        hostname_or_id,
        insights_id,
        provider_id,
        provider_type,
        updated_start,
        updated_end,
        group_name,
        None,
        tags,
        staleness,
        registered_with,
        filter,
        rbac_filter,
    )
    host_list = [str(res[0]) for res in _find_hosts_entities_query(base_query, [Host.id]).filter(*all_filters).all()]
    db.session.close()
    return host_list


def get_hosts_to_export(
    identity: object, filters: object = {}, export_format: str = "json", rbac_filter: dict = {}, batch_size: int = 0
) -> Iterator[dict]:
    st_timestamps = staleness_timestamps()
    staleness = get_staleness_obj(identity)

    q_filters, _ = query_filters(
        filter=filters, rbac_filter=rbac_filter, staleness=ALL_STALENESS_STATES, identity=identity
    )
    columns = [
        Host.id,
        Host.account,
        Host.org_id,
        Host.display_name,
        Host.host_type,
        Host.system_profile_facts,
        Host.modified_on,
        Host.facts,
        Host.reporter,
        Host.created_on,
        Host.groups,
    ]

    export_host_query = _find_hosts_model_query(identity=identity, columns=columns).filter(*q_filters)
    export_host_query = export_host_query.execution_options(yield_per=batch_size)

    num_hosts = export_host_query.count()
    logger.debug(f"Number of hosts to be exported: {num_hosts}")

    for host in db.session.scalars(export_host_query):
        yield serialize_host_for_export_svc(host, staleness_timestamps=st_timestamps, staleness=staleness)

    db.session.close()

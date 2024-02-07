from typing import List
from typing import Tuple

from sqlalchemy import func
from sqlalchemy.orm import Query
from sqlalchemy.sql.expression import ColumnElement

from api.filtering.db_filters import host_id_list_filter
from api.filtering.db_filters import query_filters
from api.filtering.db_filters import rbac_permissions_filter
from app import db
from app.auth import get_current_identity
from app.instrumentation import log_get_host_list_succeeded
from app.logging import get_logger
from app.models import Group
from app.models import Host
from app.models import HostGroupAssoc
from lib.host_repository import update_query_for_owner_id

__all__ = (
    "get_all_hosts",
    "get_host_list",
    "get_host_list_by_id_list",
    "get_host_tags_list_by_id_list",
    "params_to_order_by",
)

logger = get_logger(__name__)


def get_all_hosts() -> List:
    query = _find_all_hosts()
    query_results = query.all()
    ids_list = [str(host.id) for host in query_results]

    log_get_host_list_succeeded(logger, ids_list)
    return ids_list


def _get_host_list_using_filters(
    all_filters: List, page: int, per_page: int, param_order_by: str, param_order_how: str, fields: List[str]
) -> Tuple[List[Host], int, Tuple[str], List[str]]:
    host_query = _find_all_hosts().filter(*all_filters).order_by(*params_to_order_by(param_order_by, param_order_how))

    query_results = host_query.paginate(page, per_page, True)

    # TODO: additional_fields and system_profile_fields
    additional_fields = tuple()
    system_profile_fields = tuple()

    return query_results.items, query_results.total, additional_fields, system_profile_fields


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
    all_filters = query_filters(
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

    return _get_host_list_using_filters(all_filters, page, per_page, param_order_by, param_order_how, fields)


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

    return _get_host_list_using_filters(all_filters, page, per_page, param_order_by, param_order_how, fields)


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
            ordering = (_order_how(Group.name, order_how),)
        else:
            ordering = (Group.name.asc(),)
    elif order_by == "operating_system":
        if order_how:
            ordering = (_order_how(Host.operating_system, order_how),)
        else:
            ordering = (Host.operating_system.asc(),)
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


def _find_all_hosts(columns: List[ColumnElement] = None) -> Query:
    identity = get_current_identity()
    query = (
        Host.query.join(HostGroupAssoc, isouter=True)
        .join(Group, isouter=True)
        .filter(Host.org_id == identity.org_id)
        .group_by(Host.id, Group.name)
    )
    if columns:
        query = query.with_entities(*columns)
    return update_query_for_owner_id(identity, query)


def get_host_tags_list_by_id_list(
    host_id_list: List[str], limit: int, offset: int, order_by: str, order_how: str, rbac_filter: dict
) -> Tuple[dict, int]:
    columns = [Host.id, Host.tags]
    query = _find_all_hosts(columns)
    host_filter = host_id_list_filter(host_id_list=host_id_list)
    order = params_to_order_by(order_by, order_how)
    query_results = query.filter(*host_filter).order_by(*order).offset(offset).limit(limit).all()
    host_tags_dict = _expand_host_tags(query_results)
    return host_tags_dict, len(host_id_list)


def _expand_host_tags(hosts: List[Host]) -> dict:
    host_tags_dict = {}
    for host in hosts:
        host_tags = []
        host_namespace_tags_dict = host.tags
        for host_namespace, host_namespace_tags in host_namespace_tags_dict.items():
            for tag_key, tag_values in host_namespace_tags.items():
                for tag_value in tag_values:
                    host_tag_obj = {"namespace": host_namespace, "key": tag_key, "value": tag_value}
                    host_tags.append(host_tag_obj)
        host_tags_dict[host.id] = host_tags
    return host_tags_dict


def get_os_info(limit, offset, staleness, tags, registered_with, filter, rbac_filter):
    columns = [
        Host.system_profile_facts["operating_system"]["name"].label("name"),
        Host.system_profile_facts["operating_system"]["major"].label("major"),
        Host.system_profile_facts["operating_system"]["minor"].label("minor"),
    ]
    os_query = _find_all_hosts(columns)
    filters = query_filters(
        tags=tags, staleness=staleness, registered_with=registered_with, filter=filter, rbac_filter=rbac_filter
    )
    if filters:
        os_query = os_query.filter(*filters)

    subquery = os_query.subquery()
    agg_query = db.session.query(subquery, func.count()).group_by("name", "major", "minor")
    query_total = agg_query.count()
    query_results = agg_query.offset(offset).limit(limit).all()
    result = [{"value": {"name": qr[0], "major": qr[1], "minor": qr[2]}, "count": qr[3]} for qr in query_results]
    return result, query_total

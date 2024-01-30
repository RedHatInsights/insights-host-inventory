from typing import List
from uuid import UUID

from dateutil import parser
from sqlalchemy import and_
from sqlalchemy import or_

from app.auth import get_current_identity
from app.instrumentation import log_get_host_list_succeeded
from app.logging import get_logger
from app.models import Group
from app.models import Host
from app.models import HostGroupAssoc
from app.utils import Tag
from lib.host_repository import get_host_list_by_id_list_from_db
from lib.host_repository import update_query_for_owner_id

__all__ = ("get_all_hosts", "params_to_order_by")

NULL = None

logger = get_logger(__name__)


def get_all_hosts():
    query = _find_all_hosts()
    query_results = query.all()
    ids_list = [str(host.id) for host in query_results]

    log_get_host_list_succeeded(logger, ids_list)
    return ids_list


def _canonical_fact_filter(canonical_fact, value):
    return [Host.canonical_facts[canonical_fact].astext == value]


def _display_name_filter(display_name):
    return [Host.display_name.comparator.contains(display_name)]


def _tags_filter(string_tags):
    tags = []

    for string_tag in string_tags:
        tags.append(Tag.from_string(string_tag))

    tags_to_find = Tag.create_nested_from_tags(tags)

    return [Host.tags.contains(tags_to_find)]


def _group_names_filter(group_name_list):
    _query_filter = []
    if len(group_name_list) > 0:
        group_filters = [Group.name.in_(group_name_list)]
        if "" in group_name_list:
            group_filters += [HostGroupAssoc.group_id.is_(None)]

        _query_filter += (or_(*group_filters),)

    return _query_filter


def _group_ids_filter(group_id_list):
    _query_filter = []
    if len(group_id_list) > 0:
        group_filters = [HostGroupAssoc.group_id.in_(group_id_list)]
        if None in group_id_list:
            group_filters += [HostGroupAssoc.group_id.is_(None)]

        _query_filter += [or_(*group_filters)]

    return _query_filter


def _staleness_filter(staleness):
    _query_filter = []
    # TODO
    return _query_filter


def _registered_with_filter(registered_with):
    _query_filter = []
    # TODO
    return _query_filter


def _system_profile_filter(sp_filter):
    _query_filter = []
    # TODO
    return _query_filter


def _hostname_or_id_filter(hostname_or_id):
    filter_list = [
        Host.display_name.comparator.contains(hostname_or_id),
        Host.canonical_facts["fqdn"].astext.contains(hostname_or_id),
    ]

    try:
        UUID(hostname_or_id)
        host_id = hostname_or_id
        filter_list.append(Host.id == host_id)
        logger.debug("Adding id (uuid) to the filter list")
    except Exception:
        # Do not filter using the id
        logger.debug("The hostname (%s) could not be converted into a UUID", hostname_or_id, exc_info=True)

    return (or_(*filter_list),)


def _modified_on_filter(updated_start: str, updated_end: str) -> List:
    modified_on_filter = []
    updated_start_date = parser.isoparse(updated_start) if updated_start else None
    updated_end_date = parser.isoparse(updated_end) if updated_end else None

    if updated_start_date and updated_end_date and updated_start_date > updated_end_date:
        raise ValueError("updated_start cannot be after updated_end.")

    if updated_start_date and updated_start_date.year > 1970:
        modified_on_filter += [Host.modified_on >= updated_start_date]
    if updated_end_date and updated_end_date.year > 1970:
        modified_on_filter += [Host.modified_on <= updated_end_date]

    return [and_(*modified_on_filter)]


def _host_id_list_filter(host_id_list):
    return [Host.id.in_(host_id_list)]


def _rbac_filter(rbac_filter):
    _query_filter = []
    if rbac_filter and "groups" in rbac_filter:
        _query_filter = _group_ids_filter(rbac_filter["groups"])

    return _query_filter


def query_filters(
    fqdn=None,
    display_name=None,
    hostname_or_id=None,
    insights_id=None,
    provider_id=None,
    provider_type=None,
    updated_start=None,
    updated_end=None,
    group_name=None,
    group_ids=None,
    tags=None,
    staleness=None,
    registered_with=None,
    filter=None,
    rbac_filter=None,
):
    filters = []
    if fqdn:
        filters += _canonical_fact_filter("fqdn", fqdn)
    elif display_name:
        filters += _display_name_filter(display_name)
    elif hostname_or_id:
        filters += _hostname_or_id_filter(hostname_or_id)
    elif insights_id:
        filters += _canonical_fact_filter("insights_id", insights_id)

    if provider_id:
        filters += _canonical_fact_filter("provider_id", provider_id)
    if provider_type:
        filters += _canonical_fact_filter("provider_type", provider_type)
    if updated_start or updated_end:
        filters += _modified_on_filter(updated_start, updated_end)
    if group_name:
        filters += _group_names_filter(group_name)
    if group_ids:
        filters += _group_ids_filter(group_ids)
    if tags:
        filters += _tags_filter(tags)
    if staleness:
        filters += _staleness_filter(staleness)
    if registered_with:
        filters += _registered_with_filter(registered_with)
    if filter:
        filters += _system_profile_filter(filter)
    if rbac_filter:
        filters += _rbac_filter(rbac_filter)

    return filters


def _get_host_list_using_filters(all_filters, page, per_page, param_order_by, param_order_how, fields):
    host_query = _find_all_hosts().filter(*all_filters).order_by(*params_to_order_by(param_order_by, param_order_how))

    query_results = host_query.paginate(page, per_page, True)

    # TODO: additional_fields and system_profile_fields
    additional_fields = tuple()
    system_profile_fields = tuple()

    return query_results.items, query_results.total, additional_fields, system_profile_fields


def get_host_list(
    display_name,
    fqdn,
    hostname_or_id,
    insights_id,
    provider_id,
    provider_type,
    updated_start,
    updated_end,
    group_name,
    tags,
    page,
    per_page,
    param_order_by,
    param_order_how,
    staleness,
    registered_with,
    filter,
    fields,
    rbac_filter,
):
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
    host_id_list, page, per_page, param_order_by, param_order_how, fields=None, rbac_filter=None
):
    all_filters = _host_id_list_filter(host_id_list)
    all_filters += rbac_filter

    return _get_host_list_using_filters(all_filters, page, per_page, param_order_by, param_order_how, fields)


def params_to_order_by(order_by=None, order_how=None):
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
    elif order_by:
        raise ValueError('Unsupported ordering column, use "updated" or "display_name".')
    elif order_how:
        raise ValueError(
            "Providing ordering direction without a column is not supported. "
            "Provide order_by={updated,display_name}."
        )

    return ordering + modified_on_ordering + (Host.id.desc(),)


def _order_how(column, order_how):
    if order_how == "ASC":
        return column.asc()
    elif order_how == "DESC":
        return column.desc()
    else:
        raise ValueError('Unsupported ordering direction, use "ASC" or "DESC".')


def _find_all_hosts():
    identity = get_current_identity()
    query = (
        Host.query.join(HostGroupAssoc, isouter=True)
        .join(Group, isouter=True)
        .filter(Host.org_id == identity.org_id)
        .group_by(Host.id)
    )
    return update_query_for_owner_id(identity, query)


def get_host_tags_list_by_id_list(host_id_list, page, per_page, order_by, order_how, rbac_filter):
    columns = [Host.id, Host.tags]
    query = get_host_list_by_id_list_from_db(host_id_list, rbac_filter, columns)
    order = params_to_order_by(order_by, order_how)
    query_results = query.order_by(*order).offset((page - 1) * per_page).limit(per_page).all()
    host_tags_dict = _expand_host_tags(query_results)
    return host_tags_dict, len(host_id_list)


def _expand_host_tags(hosts):
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

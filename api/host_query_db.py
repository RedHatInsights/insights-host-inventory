from uuid import UUID

import flask
from sqlalchemy import and_
from sqlalchemy import or_

from app.auth import get_current_identity
from app.instrumentation import log_get_host_list_succeeded
from app.logging import get_logger
from app.models import Host
from app.utils import Tag
from lib.host_repository import find_hosts_by_staleness
from lib.host_repository import single_canonical_fact_host_query
from lib.host_repository import update_query_for_owner_id

__all__ = ("get_host_list", "params_to_order_by")

NULL = None

logger = get_logger(__name__)


def get_host_list(
    display_name,
    fqdn,
    hostname_or_id,
    insights_id,
    provider_id,
    provider_type,
    tags,
    page,
    per_page,
    order_by,
    order_how,
    staleness,
    registered_with,
    filter,
    fields,
):
    if filter:
        logger.error("xjoin-search not accessible")
        flask.abort(503)

    if fqdn:
        query = _find_hosts_by_canonical_fact("fqdn", fqdn.casefold())
    elif display_name:
        query = _find_hosts_by_display_name(display_name)
    elif hostname_or_id:
        query = _find_hosts_by_hostname_or_id(hostname_or_id)
    elif insights_id:
        query = _find_hosts_by_canonical_fact("insights_id", insights_id.casefold())
    else:
        query = _find_all_hosts()

    if tags:
        # add tag filtering to the query
        query = _find_hosts_by_tag(tags, query)

    if staleness is None:
        staleness = ["fresh", "stale", "unknown"]
    if staleness:
        query = find_hosts_by_staleness(staleness, query)

    if registered_with:
        query = find_hosts_with_insights_enabled(query)

    order_by = params_to_order_by(order_by, order_how)
    query = query.order_by(*order_by)
    query_results = query.paginate(page, per_page, True)
    additional_fields = tuple()

    log_get_host_list_succeeded(logger, query_results.items)

    return query_results.items, query_results.total, additional_fields


def find_hosts_with_insights_enabled(query):
    return query.filter(Host.canonical_facts["insights_id"].isnot(NULL))


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
    query = Host.query.filter(Host.account == identity.account_number)
    return update_query_for_owner_id(identity, query)


def _find_hosts_by_canonical_fact(canonical_fact, value):
    return single_canonical_fact_host_query(get_current_identity(), canonical_fact, value)


def _find_hosts_by_tag(string_tags, query):
    logger.debug("_find_hosts_by_tag(%s)", string_tags)

    tags = []

    for string_tag in string_tags:
        tags.append(Tag.from_string(string_tag))

    tags_to_find = Tag.create_nested_from_tags(tags)

    return query.filter(Host.tags.contains(tags_to_find))


def _find_hosts_by_hostname_or_id(hostname):
    current_identity = get_current_identity()
    logger.debug("_find_hosts_by_hostname_or_id(%s)", hostname)

    filter_list = [
        Host.display_name.comparator.contains(hostname),
        Host.canonical_facts["fqdn"].astext.contains(hostname.casefold()),
    ]

    try:
        UUID(hostname)
        host_id = hostname
        filter_list.append(Host.id == host_id)
        logger.debug("Adding id (uuid) to the filter list")
    except Exception:
        # Do not filter using the id
        logger.debug("The hostname (%s) could not be converted into a UUID", hostname, exc_info=True)

    return Host.query.filter(and_(*[Host.account == current_identity.account_number, or_(*filter_list)]))


def _find_hosts_by_display_name(display_name):

    current_identity = get_current_identity()
    logger.debug("find_hosts_by_display_name(%s)", display_name)
    return Host.query.filter(
        and_(Host.account == current_identity.account_number, Host.display_name.comparator.contains(display_name))
    )

from uuid import UUID

from sqlalchemy import and_
from sqlalchemy import or_

from app import inventory_config
from app.auth import current_identity
from app.culling import staleness_to_conditions
from app.logging import get_logger
from app.models import Host
from app.utils import Tag
from lib.host_repository import canonical_facts_host_query

__all__ = ("get_host_list", "find_hosts_by_staleness", "params_to_order_by")

NULL = None

logger = get_logger(__name__)


def get_host_list(
    display_name, fqdn, hostname_or_id, insights_id, tags, page, per_page, order_by, order_how, staleness
):
    if fqdn:
        query = _find_hosts_by_canonical_facts({"fqdn": fqdn})
    elif display_name:
        query = _find_hosts_by_display_name(display_name)
    elif hostname_or_id:
        query = _find_hosts_by_hostname_or_id(hostname_or_id)
    elif insights_id:
        query = _find_hosts_by_canonical_facts({"insights_id": insights_id})
    else:
        query = _find_all_hosts()

    if tags:
        # add tag filtering to the query
        query = _find_hosts_by_tag(tags, query)

    if staleness:
        query = find_hosts_by_staleness(staleness, query)

    order_by = params_to_order_by(order_by, order_how)
    query = query.order_by(*order_by)
    query_results = query.paginate(page, per_page, True)

    logger.debug("Found hosts: %s", query_results.items)

    return query_results.items, query_results.total


def find_hosts_by_staleness(staleness, query):
    logger.debug("find_hosts_by_staleness(%s)", staleness)
    config = inventory_config()
    staleness_conditions = tuple(staleness_to_conditions(config, staleness, _stale_timestamp_filter))
    if "unknown" in staleness:
        staleness_conditions += (Host.stale_timestamp == NULL,)

    return query.filter(or_(*staleness_conditions))


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
    return Host.query.filter(Host.account == current_identity.account_number)


def _find_hosts_by_canonical_facts(canonical_facts):
    return canonical_facts_host_query(current_identity.account_number, canonical_facts)


def _find_hosts_by_tag(string_tags, query):
    logger.debug("_find_hosts_by_tag(%s)", string_tags)

    tags = []

    for string_tag in string_tags:
        tags.append(Tag().from_string(string_tag))

    tags_to_find = Tag.create_nested_from_tags(tags)

    return query.filter(Host.tags.contains(tags_to_find))


def _find_hosts_by_hostname_or_id(hostname):
    logger.debug("_find_hosts_by_hostname_or_id(%s)", hostname)

    filter_list = [
        Host.display_name.comparator.contains(hostname),
        Host.canonical_facts["fqdn"].astext.contains(hostname),
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
    logger.debug("find_hosts_by_display_name(%s)", display_name)
    return Host.query.filter(
        and_(Host.account == current_identity.account_number, Host.display_name.comparator.contains(display_name))
    )


def _stale_timestamp_filter(gte=None, lte=None):
    filter_ = ()
    if gte:
        filter_ += (Host.stale_timestamp >= gte,)
    if lte:
        filter_ += (Host.stale_timestamp <= lte,)
    return and_(*filter_)

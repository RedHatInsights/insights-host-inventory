from uuid import UUID

from app.logging import get_logger
from app.serialization import deserialize_host_xjoin as deserialize_host
from app.utils import Tag
from app.xjoin import check_pagination
from app.xjoin import graphql_query
from app.xjoin import pagination_params
from app.xjoin import staleness_filter
from app.xjoin import string_contains

__all__ = ("get_host_list",)

logger = get_logger(__name__)


QUERY = """query Query(
    $limit: Int!,
    $offset: Int!,
    $order_by: HOSTS_ORDER_BY,
    $order_how: ORDER_DIR,
    $filter: [HostFilter!]
) {
    hosts(
        limit: $limit,
        offset: $offset,
        order_by: $order_by,
        order_how: $order_how,
        filter: {
            AND: $filter,
        }
    ) {
        meta {
            total,
        }
        data {
            id,
            account,
            display_name,
            ansible_host,
            created_on,
            modified_on,
            canonical_facts,
            facts,
            stale_timestamp,
            reporter,
        }
    }
}"""
ORDER_BY_MAPPING = {None: "modified_on", "updated": "modified_on", "display_name": "display_name"}
ORDER_HOW_MAPPING = {"modified_on": "DESC", "display_name": "ASC"}


def get_host_list(
    display_name,
    fqdn,
    hostname_or_id,
    insights_id,
    tags,
    page,
    per_page,
    param_order_by,
    param_order_how,
    staleness,
    registered_with,
):
    limit, offset = pagination_params(page, per_page)
    xjoin_order_by, xjoin_order_how = _params_to_order(param_order_by, param_order_how)

    variables = {
        "limit": limit,
        "offset": offset,
        "order_by": xjoin_order_by,
        "order_how": xjoin_order_how,
        "filter": _query_filters(fqdn, display_name, hostname_or_id, insights_id, tags, staleness, registered_with),
    }
    response = graphql_query(QUERY, variables)["hosts"]

    total = response["meta"]["total"]
    check_pagination(offset, total)

    return map(deserialize_host, response["data"]), total


def _params_to_order(param_order_by=None, param_order_how=None):
    if param_order_how and not param_order_by:
        raise ValueError(
            "Providing ordering direction without a column is not supported. "
            "Provide order_by={updated,display_name}."
        )

    xjoin_order_by = ORDER_BY_MAPPING[param_order_by]
    xjoin_order_how = param_order_how or ORDER_HOW_MAPPING[xjoin_order_by]
    return xjoin_order_by, xjoin_order_how


def _query_filters(fqdn, display_name, hostname_or_id, insights_id, tags, staleness, registered_with):
    if fqdn:
        query_filters = ({"fqdn": fqdn},)
    elif display_name:
        query_filters = ({"display_name": string_contains(display_name)},)
    elif hostname_or_id:
        contains = string_contains(hostname_or_id)
        hostname_or_id_filters = ({"display_name": contains}, {"fqdn": contains})
        try:
            id = UUID(hostname_or_id)
        except ValueError:
            # Do not filter using the id
            logger.debug("The hostname (%s) could not be converted into a UUID", hostname_or_id, exc_info=True)
        else:
            logger.debug("Adding id (uuid) to the filter list")
            hostname_or_id_filters += ({"id": str(id)},)
        query_filters = ({"OR": hostname_or_id_filters},)
    elif insights_id:
        query_filters = ({"insights_id": insights_id},)
    else:
        query_filters = ()

    if tags:
        query_filters += tuple({"tag": Tag().from_string(string_tag).data()} for string_tag in tags)
    if staleness:
        staleness_filters = tuple(staleness_filter(staleness))
        query_filters += ({"OR": staleness_filters},)
    return query_filters

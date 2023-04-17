import flask

from api.filtering.filtering import host_id_list_query_filter
from api.filtering.filtering import query_filters
from app.instrumentation import log_get_host_list_failed
from app.logging import get_logger
from app.serialization import deserialize_host_xjoin as deserialize_host
from app.xjoin import check_pagination
from app.xjoin import graphql_query
from app.xjoin import pagination_params
from app.xjoin import params_to_order

__all__ = ("get_host_list", "get_host_ids_list", "query_filters")

logger = get_logger(__name__)

NIL_STRING = "nil"
NOT_NIL_STRING = "not_nil"
QUERY = """query Query(
    $limit: Int!,
    $offset: Int!,
    $order_by: HOSTS_ORDER_BY,
    $order_how: ORDER_DIR,
    $filter: [HostFilter!],
    $fields: [String!]
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
            org_id,
            display_name,
            ansible_host,
            created_on,
            modified_on,
            canonical_facts,
            facts,
            stale_timestamp,
            reporter,
            per_reporter_staleness,
            system_profile_facts (filter: $fields),
        }
    }
}"""
HOST_TAGS_QUERY = """query Query(
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
            tags {
                data {
                    namespace, key, value
                }
            },
        }
    }
}"""
HOST_IDS_QUERY = """query Query(
    $limit: Int!,
    $offset: Int!,
    $filter: [HostFilter!],
) {
    hosts(
        limit: $limit,
        offset: $offset,
        filter: {
            AND: $filter,
        }
    ) {
        meta {
            total,
        }
        data {
            id,
            canonical_facts
        }
    }
}"""


def get_host_list_using_filters(all_filters, page, per_page, param_order_by, param_order_how, fields=None):
    limit, offset = pagination_params(page, per_page)
    xjoin_order_by, xjoin_order_how = params_to_order(param_order_by, param_order_how)

    additional_fields = tuple()

    system_profile_fields = []
    if fields and fields.get("system_profile"):
        additional_fields = ("system_profile",)
        system_profile_fields = list(fields.get("system_profile").keys())

    variables = {
        "limit": limit,
        "offset": offset,
        "order_by": xjoin_order_by,
        "order_how": xjoin_order_how,
        "filter": all_filters,
        "fields": system_profile_fields,
    }
    response = graphql_query(QUERY, variables, log_get_host_list_failed)
    if response is None or "hosts" not in response:
        # Log an error implicating xjoin, then abort with status 503
        logger.error("xjoin-search responded with invalid format")
        flask.abort(503)

    response = response["hosts"]

    total = response["meta"]["total"]
    check_pagination(offset, total)

    return map(deserialize_host, response["data"]), total, additional_fields


def get_host_tags_list_using_filters(all_filters, page, per_page, param_order_by, param_order_how):
    limit, offset = pagination_params(page, per_page)
    xjoin_order_by, xjoin_order_how = params_to_order(param_order_by, param_order_how)

    variables = {
        "limit": limit,
        "offset": offset,
        "order_by": xjoin_order_by,
        "order_how": xjoin_order_how,
        "filter": all_filters,
    }
    response = graphql_query(HOST_TAGS_QUERY, variables, log_get_host_list_failed)
    if response is None or "hosts" not in response:
        # Log an error implicating xjoin, then abort with status 503
        logger.error("xjoin-search responded with invalid format")
        flask.abort(503)

    response = response["hosts"]

    total = response["meta"]["total"]
    check_pagination(offset, total)

    return {host["id"]: host["tags"]["data"] for host in response["data"]}, total


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
    )

    return get_host_list_using_filters(all_filters, page, per_page, param_order_by, param_order_how, fields)


def get_host_list_by_id_list(host_id_list, page, per_page, param_order_by, param_order_how, fields=None):
    all_filters = host_id_list_query_filter(host_id_list)

    return get_host_list_using_filters(all_filters, page, per_page, param_order_by, param_order_how, fields)


def get_host_tags_list_by_id_list(host_id_list, page, per_page, param_order_by, param_order_how):
    all_filters = host_id_list_query_filter(host_id_list)

    return get_host_tags_list_using_filters(all_filters, page, per_page, param_order_by, param_order_how)


def get_host_ids_list(
    display_name,
    fqdn,
    hostname_or_id,
    insights_id,
    provider_id,
    provider_type,
    updated_start,
    updated_end,
    group_name,
    registered_with,
    staleness,
    tags,
    filter,
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
    )

    id_list = []
    offset = 0
    total = 1
    # Get the list of IDs from xjoin, 100 at a time (since that's the max xjoin can return).
    while offset < total:
        variables = {"limit": 100, "offset": offset, "filter": all_filters}
        response = graphql_query(HOST_IDS_QUERY, variables, log_get_host_list_failed)["hosts"]
        total = int(response["meta"]["total"])
        id_list.extend([x["id"] for x in response["data"]])
        # Next loop, query the next 100 records.
        offset += 100

    return id_list

from api.filtering.filtering import query_filters
from app.auth import get_current_identity
from app.auth.identity import IdentityType
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
            display_name,
            ansible_host,
            created_on,
            modified_on,
            canonical_facts,
            facts,
            stale_timestamp,
            reporter,
            system_profile_facts (filter: $fields),
        }
    }
}"""
HOST_IDS_QUERY = """query Query(
    $limit: Int!,
    $filter: [HostFilter!],
) {
    hosts(
        limit: $limit,
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
    param_order_by,
    param_order_how,
    staleness,
    registered_with,
    filter,
    fields,
):
    limit, offset = pagination_params(page, per_page)
    xjoin_order_by, xjoin_order_how = params_to_order(param_order_by, param_order_how)

    all_filters = query_filters(
        fqdn,
        display_name,
        hostname_or_id,
        insights_id,
        provider_id,
        provider_type,
        tags,
        staleness,
        registered_with,
        filter,
    )

    current_identity = get_current_identity()
    if current_identity.identity_type == IdentityType.SYSTEM:
        all_filters += owner_id_filter()

    additional_fields = tuple()

    system_profile_fields = []
    if fields.get("system_profile"):
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
    response = graphql_query(QUERY, variables, log_get_host_list_failed)["hosts"]

    total = response["meta"]["total"]
    check_pagination(offset, total)

    return map(deserialize_host, response["data"]), total, additional_fields


def get_host_ids_list(
    display_name,
    fqdn,
    hostname_or_id,
    insights_id,
    provider_id,
    provider_type,
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
        tags,
        staleness,
        registered_with,
        filter,
    )

    current_identity = get_current_identity()
    if current_identity.identity_type == IdentityType.SYSTEM:
        all_filters += owner_id_filter()

    variables = {"limit": 100, "filter": all_filters}  # maximum limit handled by xjoin.
    response = graphql_query(HOST_IDS_QUERY, variables, log_get_host_list_failed)["hosts"]

    return [x["id"] for x in response["data"]]


def owner_id_filter():
    return ({"spf_owner_id": {"eq": get_current_identity().system["cn"]}},)

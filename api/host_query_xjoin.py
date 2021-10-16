from api.filtering.filtering import query_filters
from app.auth import get_current_identity
from app.auth.identity import AuthType
from app.auth.identity import IdentityType
from app.instrumentation import log_get_host_list_failed
from app.logging import get_logger
from app.serialization import deserialize_host_xjoin as deserialize_host
from app.xjoin import check_pagination
from app.xjoin import graphql_query
from app.xjoin import pagination_params

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
    $filter: [HostFilter!],
) {
    hosts(
        filter: {
            AND: $filter,
        }
    ) {
        meta {
            total,
        }
        data {
            id,
        }
    }
}"""
ORDER_BY_MAPPING = {None: "modified_on", "updated": "modified_on", "display_name": "display_name"}
ORDER_HOW_MAPPING = {"modified_on": "DESC", "display_name": "ASC"}
SUPPORTED_RANGE_OPERATIONS = ["gt", "gte", "lt", "lte"]


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
    xjoin_order_by, xjoin_order_how = _params_to_order(param_order_by, param_order_how)

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
    if current_identity.identity_type == IdentityType.SYSTEM and current_identity.auth_type != AuthType.CLASSIC:
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


def get_host_ids_list(display_name, fqdn, hostname_or_id, insights_id, provider_id, provider_type, tags, filter):
    # registered_with and staleness required only to build query_filters
    registered_with = None
    staleness = None
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
    if current_identity.identity_type == IdentityType.SYSTEM and current_identity.auth_type != AuthType.CLASSIC:
        all_filters += owner_id_filter()

    variables = {"filter": all_filters}
    response = graphql_query(HOST_IDS_QUERY, variables, log_get_host_list_failed)["hosts"]

    return response["data"], response["meta"]["total"]


def _params_to_order(param_order_by=None, param_order_how=None):
    if param_order_how and not param_order_by:
        raise ValueError(
            "Providing ordering direction without a column is not supported. "
            "Provide order_by={updated,display_name}."
        )

    xjoin_order_by = ORDER_BY_MAPPING[param_order_by]
    xjoin_order_how = param_order_how or ORDER_HOW_MAPPING[xjoin_order_by]
    return xjoin_order_by, xjoin_order_how


def owner_id_filter():
    return ({"spf_owner_id": {"eq": get_current_identity().system["cn"]}},)

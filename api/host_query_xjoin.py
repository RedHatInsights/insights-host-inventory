from uuid import UUID

from api.filtering.filtering import build_system_profile_filter
from app.auth import get_current_identity
from app.auth.identity import AuthType
from app.auth.identity import IdentityType
from app.exceptions import ValidationException
from app.instrumentation import log_get_host_list_failed
from app.logging import get_logger
from app.serialization import deserialize_host_xjoin as deserialize_host
from app.utils import Tag
from app.xjoin import check_pagination
from app.xjoin import graphql_query
from app.xjoin import pagination_params
from app.xjoin import staleness_filter
from app.xjoin import string_contains
from app.xjoin import string_contains_lc

__all__ = ("get_host_list",)

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
ORDER_BY_MAPPING = {None: "modified_on", "updated": "modified_on", "display_name": "display_name"}
ORDER_HOW_MAPPING = {"modified_on": "DESC", "display_name": "ASC"}
SUPPORTED_RANGE_OPERATIONS = ["gt", "gte", "lt", "lte"]


def build_tag_query_dict_tuple(tags):
    query_tag_tuple = ()
    for string_tag in tags:
        query_tag_dict = {}
        tag_dict = Tag.from_string(string_tag).data()
        for key in tag_dict.keys():
            query_tag_dict[key] = {"eq": tag_dict[key]}
        query_tag_tuple += ({"tag": query_tag_dict},)
    logger.debug("query_tag_tuple: %s", query_tag_tuple)
    return query_tag_tuple


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

    all_filters = _query_filters(
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


def _params_to_order(param_order_by=None, param_order_how=None):
    if param_order_how and not param_order_by:
        raise ValueError(
            "Providing ordering direction without a column is not supported. "
            "Provide order_by={updated,display_name}."
        )

    xjoin_order_by = ORDER_BY_MAPPING[param_order_by]
    xjoin_order_how = param_order_how or ORDER_HOW_MAPPING[xjoin_order_by]
    return xjoin_order_by, xjoin_order_how


def _query_filters(
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
):
    if fqdn:
        query_filters = ({"fqdn": {"eq": fqdn}},)
    elif display_name:
        query_filters = ({"display_name": string_contains_lc(display_name)},)
    elif hostname_or_id:
        contains = string_contains(hostname_or_id)
        contains_lc = string_contains_lc(hostname_or_id)
        hostname_or_id_filters = ({"display_name": contains_lc}, {"fqdn": contains})
        try:
            id = UUID(hostname_or_id)
        except ValueError:
            # Do not filter using the id
            logger.debug("The hostname (%s) could not be converted into a UUID", hostname_or_id, exc_info=True)
        else:
            logger.debug("Adding id (uuid) to the filter list")
            hostname_or_id_filters += ({"id": {"eq": str(id)}},)
        query_filters = ({"OR": hostname_or_id_filters},)
    elif insights_id:
        query_filters = ({"insights_id": {"eq": insights_id}},)
    else:
        query_filters = ()

    if tags:
        query_filters += build_tag_query_dict_tuple(tags)
    if staleness:
        staleness_filters = tuple(staleness_filter(staleness))
        query_filters += ({"OR": staleness_filters},)
    if registered_with:
        query_filters += ({"NOT": {"insights_id": {"eq": None}}},)
    if provider_type:
        query_filters += ({"provider_type": {"eq": provider_type}},)
    if provider_id:
        query_filters += ({"provider_id": {"eq": provider_id}},)

    for key in filter:
        if key == "system_profile":
            query_filters += build_system_profile_filter(filter["system_profile"])
        else:
            raise ValidationException("filter key is invalid")

    logger.debug(query_filters)
    return query_filters


def owner_id_filter():
    return ({"spf_owner_id": {"eq": get_current_identity().system["cn"]}},)

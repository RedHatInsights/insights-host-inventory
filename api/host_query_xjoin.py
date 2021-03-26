from uuid import UUID

from app.auth import get_current_identity
from app.auth.identity import AuthType
from app.auth.identity import IdentityType
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
    tags,
    page,
    per_page,
    param_order_by,
    param_order_how,
    staleness,
    registered_with,
    filter,
):
    limit, offset = pagination_params(page, per_page)
    xjoin_order_by, xjoin_order_how = _params_to_order(param_order_by, param_order_how)

    all_filters = _query_filters(
        fqdn, display_name, hostname_or_id, insights_id, tags, staleness, registered_with, filter
    )

    current_identity = get_current_identity()
    if current_identity.identity_type == IdentityType.SYSTEM and current_identity.auth_type != AuthType.CLASSIC:
        all_filters += owner_id_filter()

    variables = {
        "limit": limit,
        "offset": offset,
        "order_by": xjoin_order_by,
        "order_how": xjoin_order_how,
        "filter": all_filters,
    }
    response = graphql_query(QUERY, variables, log_get_host_list_failed)["hosts"]

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


def _nullable_wrapper(field_name, field_value, graphql_operation, filter_function):
    if field_value == NIL_STRING:
        return ({field_name: {graphql_operation: None}},)
    elif field_value == NOT_NIL_STRING:
        return ({"NOT": {field_name: {graphql_operation: None}}},)
    else:
        return filter_function(field_name, field_value)


def _nullable_boolean_filter(field_name, field_value):
    return _nullable_wrapper(field_name, field_value, "is", _boolean_filter)


def _boolean_filter(field_name, field_value):
    return ({field_name: {"is": (field_value.lower() == "true")}},)


def _nullable_string_filter(field_name, field_value):
    return _nullable_wrapper(field_name, field_value, "eq", _string_filter)


def _string_filter(field_name, field_value):
    return ({field_name: {"eq": (field_value)}},)


def _nullable_wildcard_filter(field_name, field_value):
    return _nullable_wrapper(field_name, field_value, "eq", _wildcard_string_filter)


def _wildcard_string_filter(field_name, field_value):
    return ({field_name: {"matches": (field_value)}},)


def _sap_sids_filters(field_name, sap_sids):
    sap_sids_filters = ()
    for sap_sid in sap_sids:
        sap_sids_filters += ({field_name: {"eq": sap_sid}},)
    return sap_sids_filters


def build_filter(field_name, field_value, field_type, operation, filter_building_function):
    if isinstance(field_value, field_type):
        return filter_building_function(field_name, field_value)
    elif field_value.get(operation):
        return filter_building_function(field_name, field_value[operation])


def build_sap_system_filter(sap_system):
    return build_filter("spf_sap_system", sap_system, str, "eq", _nullable_boolean_filter)


def build_sap_sids_filter(sap_sids):
    return build_filter("spf_sap_sids", sap_sids, list, "contains", _sap_sids_filters)


def _query_filters(fqdn, display_name, hostname_or_id, insights_id, tags, staleness, registered_with, filter):
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

    if filter:
        if filter.get("system_profile"):
            query_filters += _build_system_profile_filter(filter["system_profile"])

    logger.debug(query_filters)
    return query_filters


def _build_system_profile_filter(system_profile):
    system_profile_filter = tuple()

    if system_profile.get("sap_system"):
        system_profile_filter += build_sap_system_filter(system_profile["sap_system"])
    if system_profile.get("sap_sids"):
        system_profile_filter += build_sap_sids_filter(system_profile["sap_sids"])
    if system_profile.get("is_marketplace"):
        system_profile_filter += build_filter(
            "spf_is_marketplace", system_profile["is_marketplace"], str, "eq", _nullable_boolean_filter
        )
    if system_profile.get("rhc_client_id"):
        system_profile_filter += build_filter(
            "spf_rhc_client_id", system_profile["rhc_client_id"], str, "eq", _nullable_string_filter
        )
    if system_profile.get("insights_client_version"):
        system_profile_filter += build_filter(
            "spf_insights_client_version",
            system_profile["insights_client_version"],
            str,
            "eq",
            _nullable_wildcard_filter,
        )

    return system_profile_filter


def owner_id_filter():
    return ({"spf_owner_id": {"eq": get_current_identity().system["cn"]}},)

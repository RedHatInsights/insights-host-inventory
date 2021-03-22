import flask

from api import api_operation
from api import build_collection_response
from api import custom_escape
from api import flask_json_response
from api import metrics
from api.host import get_bulk_query_source
from api.host_query_xjoin import build_sap_sids_filter
from api.host_query_xjoin import build_sap_system_filters
from api.host_query_xjoin import build_tag_query_dict_tuple
from api.host_query_xjoin import owner_id_filter
from app import Permission
from app.auth import get_current_identity
from app.config import BulkQuerySource
from app.instrumentation import log_get_tags_failed
from app.instrumentation import log_get_tags_succeeded
from app.logging import get_logger
from app.xjoin import check_pagination
from app.xjoin import graphql_query
from app.xjoin import pagination_params
from app.xjoin import staleness_filter
from lib.middleware import rbac


logger = get_logger(__name__)

TAGS_QUERY = """
    query hostTags (
        $hostFilter: HostFilter,
        $filter: TagAggregationFilter,
        $order_by: HOST_TAGS_ORDER_BY,
        $order_how: ORDER_DIR,
        $limit: Int,
        $offset: Int
    ) {
        hostTags (
            hostFilter: $hostFilter,
            filter: $filter,
            order_by: $order_by,
            order_how: $order_how,
            limit: $limit,
            offset: $offset
        ) {
            meta {
                total
            }
            data {
                tag {
                    namespace, key, value
                },
                count
            }
        }
    }
"""


def xjoin_enabled():
    return get_bulk_query_source() == BulkQuerySource.xjoin


@api_operation
@rbac(Permission.READ)
@metrics.api_request_time.time()
def get_tags(
    search=None,
    tags=None,
    order_by=None,
    order_how=None,
    page=None,
    per_page=None,
    staleness=None,
    registered_with=None,
    filter=None,
):
    if not xjoin_enabled():
        flask.abort(503)

    limit, offset = pagination_params(page, per_page)

    variables = {
        "order_by": order_by,
        "order_how": order_how,
        "limit": limit,
        "offset": offset,
        "hostFilter": {
            # we're not indexing null timestamps in ES
            "OR": list(staleness_filter(staleness))
        },
    }

    hostfilter_and_variables = ()

    if search:
        variables["filter"] = {
            # Escaped so that the string literals are not interpreted as regex
            "search": {"regex": f".*{custom_escape(search)}.*"}
        }

    if tags:
        hostfilter_and_variables = build_tag_query_dict_tuple(tags)

    if registered_with:
        variables["hostFilter"]["NOT"] = {"insights_id": {"eq": None}}

    if filter:
        if filter.get("system_profile"):
            if filter["system_profile"].get("sap_system"):
                hostfilter_and_variables += build_sap_system_filters(filter["system_profile"].get("sap_system"))
            if filter["system_profile"].get("sap_sids"):
                hostfilter_and_variables += build_sap_sids_filter(filter["system_profile"]["sap_sids"])

    current_identity = get_current_identity()
    if (
        current_identity.identity_type == "System"
        and current_identity.auth_type != "classic-proxy"
        and current_identity.system["cert_type"] == "system"
    ):
        hostfilter_and_variables += owner_id_filter()

    if hostfilter_and_variables != ():
        variables["hostFilter"]["AND"] = hostfilter_and_variables

    response = graphql_query(TAGS_QUERY, variables, log_get_tags_failed)
    data = response["hostTags"]

    check_pagination(offset, data["meta"]["total"])

    log_get_tags_succeeded(logger, data)
    return flask_json_response(build_collection_response(data["data"], page, per_page, data["meta"]["total"]))

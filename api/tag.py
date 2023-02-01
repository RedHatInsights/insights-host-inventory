from api import api_operation
from api import build_collection_response
from api import custom_escape
from api import flask_json_response
from api import metrics
from api.filtering.filtering import query_filters
from app import Permission
from app.instrumentation import log_get_tags_failed
from app.instrumentation import log_get_tags_succeeded
from app.logging import get_logger
from app.xjoin import check_pagination
from app.xjoin import graphql_query
from app.xjoin import pagination_params
from lib.middleware import rbac


logger = get_logger(__name__)

TAGS_QUERY = """
    query hostTags (
        $hostFilter: [HostFilter],
        $filter: TagAggregationFilter,
        $order_by: HOST_TAGS_ORDER_BY,
        $order_how: ORDER_DIR,
        $limit: Int,
        $offset: Int
    ) {
        hostTags (
            hostFilter: {
                AND: $hostFilter,
            }
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


@api_operation
@rbac(Permission.READ)
@metrics.api_request_time.time()
def get_tags(
    search=None,
    tags=None,
    display_name=None,
    fqdn=None,
    hostname_or_id=None,
    insights_id=None,
    provider_id=None,
    provider_type=None,
    order_by=None,
    order_how=None,
    page=None,
    per_page=None,
    staleness=None,
    registered_with=None,
    filter=None,
):
    limit, offset = pagination_params(page, per_page)

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

    variables = {
        "order_by": order_by,
        "order_how": order_how,
        "limit": limit,
        "offset": offset,
        "hostFilter": all_filters,
    }

    if search:
        variables["filter"] = {
            # Escaped so that the string literals are not interpreted as regex
            "search": {"regex": f".*{custom_escape(search)}.*"}
        }

    response = graphql_query(TAGS_QUERY, variables, log_get_tags_failed)
    data = response["hostTags"]

    check_pagination(offset, data["meta"]["total"])

    log_get_tags_succeeded(logger, data)
    return flask_json_response(build_collection_response(data["data"], page, per_page, data["meta"]["total"]))

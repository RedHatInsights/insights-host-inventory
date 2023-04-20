import flask

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
    updated_start=None,
    updated_end=None,
    group_name=None,
    order_by=None,
    order_how=None,
    page=None,
    per_page=None,
    staleness=None,
    registered_with=None,
    filter=None,
):
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

    try:
        hostfilter_and_variables = query_filters(
            fqdn,
            display_name,
            hostname_or_id,
            insights_id,
            provider_id,
            provider_type,
            updated_start,
            updated_end,
            group_name,
            tags,
            None,  # Staleness to not use the default values
            registered_with,
            filter,
        )
    except ValueError as e:
        log_get_tags_failed(logger)
        flask.abort(400, str(e))

    if search:
        variables["filter"] = {
            # Escaped so that the string literals are not interpreted as regex
            "search": {"regex": f".*{custom_escape(search)}.*"}
        }

    if hostfilter_and_variables != ():
        variables["hostFilter"]["AND"] = hostfilter_and_variables

    response = graphql_query(TAGS_QUERY, variables, log_get_tags_failed)
    data = response["hostTags"]

    check_pagination(offset, data["meta"]["total"])

    log_get_tags_succeeded(logger, data)
    return flask_json_response(build_collection_response(data["data"], page, per_page, data["meta"]["total"]))

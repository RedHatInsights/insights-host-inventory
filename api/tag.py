import flask

from api import api_operation
from api import build_collection_response
from api import custom_escape
from api import flask_json_response
from api import metrics
from api.filtering.filtering import query_filters
from api.host import get_bulk_query_source
from api.host_query_xjoin import owner_id_filter
from app import Permission
from app.auth import get_current_identity
from app.auth.identity import AuthType
from app.auth.identity import IdentityType
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
    if not xjoin_enabled():
        logger.error("xjoin-search not enabled")
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
    hostfilter_and_variables = query_filters(
        fqdn,
        display_name,
        hostname_or_id,
        insights_id,
        provider_id,
        provider_type,
        tags,
        [],  # use kwargs later
        registered_with,
        filter,
    )

    if search:
        variables["filter"] = {
            # Escaped so that the string literals are not interpreted as regex
            "search": {"regex": f".*{custom_escape(search)}.*"}
        }

    current_identity = get_current_identity()
    if current_identity.identity_type == IdentityType.SYSTEM and current_identity.auth_type != AuthType.CLASSIC:
        hostfilter_and_variables += owner_id_filter()

    if hostfilter_and_variables != ():
        variables["hostFilter"]["AND"] = hostfilter_and_variables

    response = graphql_query(TAGS_QUERY, variables, log_get_tags_failed)
    data = response["hostTags"]

    check_pagination(offset, data["meta"]["total"])

    log_get_tags_succeeded(logger, data)
    return flask_json_response(build_collection_response(data["data"], page, per_page, data["meta"]["total"]))

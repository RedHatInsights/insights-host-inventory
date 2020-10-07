import flask

from api import api_operation
from api import build_collection_response
from api import flask_json_response
from api import metrics
from api.host import get_bulk_query_source
from api.host_query_xjoin import build_tag_query_dict_tuple
from app import Permission
from app.config import BulkQuerySource
from app.logging import get_logger
from app.xjoin import check_pagination
from app.xjoin import graphql_query
from app.xjoin import pagination_params
from app.xjoin import staleness_filter
from lib.middleware import rbac

logger = get_logger(__name__)

# TAGS_QUERY = """
#     query hostTags (
#         $hostFilter: HostFilter,
#         $filter: TagAggregationFilter,
#         $order_by: HOST_TAGS_ORDER_BY,
#         $order_how: ORDER_DIR,
#         $limit: Int,
#         $offset: Int
#     ) {
#         hostTags (
#             hostFilter: $hostFilter,
#             filter: $filter,
#             order_by: $order_by,
#             order_how: $order_how,
#             limit: $limit,
#             offset: $offset
#         ) {
#             meta {
#                 total
#             }
#             data {
#                 tag {
#                     namespace, key, value
#                 },
#                 count
#             }
#         }
#     }
# """

SYSTEM_PROFILE_QUERY = """
    query hostSystemProfile (
        $hostFilter: HostFilter
    ) {
        hostSystemProfile (
            hostFilter: $hostFilter
        ) {
            sap_system {
                meta{
                    total
                    count
                }
                data {
                    value
                    count
                }
            }
        }
    }
"""

SYSTEM_PROFILE_QUERY = """
    query hostSystemProfile (
        $hostFilter: HostFilter
    ) {
        hostSystemProfile (
            hostFilter: $hostFilter
        ) {
            sap_sids {
                meta{
                    total
                    count
                }
                data {
                    value
                    count
                }
            }
        }
    }
"""


def xjoin_enabled():
    return get_bulk_query_source() == BulkQuerySource.xjoin


@api_operation
@rbac(Permission.READ)
@metrics.api_request_time.time()
def get_sap_system(
    # search=None,
    tags=None,
    # order_by=None,
    # order_how=None,
    page=None,
    per_page=None,
    staleness=None,
    registered_with=None,
):
    if not xjoin_enabled():
        flask.abort(503)

    limit, offset = pagination_params(page, per_page)

    variables = {
        # "order_by": order_by,
        # "order_how": order_how,
        # "limit": limit,
        # "offset": offset,
        "hostFilter": {
            # we're not indexing null timestamps in ES
            "OR": list(staleness_filter(staleness))
        }
    }

    # if search:
    #     variables["filter"] = {
    #         # Escaped so that the string literals are not interpretted as regex
    #         "search": {"regex": f".*{re.escape(search)}.*"}
    #     }

    if tags:
        variables["hostFilter"]["AND"] = build_tag_query_dict_tuple(tags)

    if registered_with:
        variables["hostFilter"]["NOT"] = {"insights_id": {"eq": None}}

    response = graphql_query(SYSTEM_PROFILE_QUERY, variables)

    print(f"response: {response}")

    data = response["hostSystemProfile"]

    check_pagination(offset, data["sap_system"]["meta"]["total"])

    return flask_json_response(
        build_collection_response(data["sap_system"], page, per_page, data["sap_system"]["meta"]["total"])
    )


@api_operation
@rbac(Permission.READ)
@metrics.api_request_time.time()
def get_sap_sids(tags=None, page=None, per_page=None, staleness=None, registered_with=None):
    if not xjoin_enabled():
        flask.abort(503)

    limit, offset = pagination_params(page, per_page)

    variables = {
        "hostFilter": {
            # we're not indexing null timestamps in ES
            "OR": list(staleness_filter(staleness))
        }
    }

    if tags:
        variables["hostFilter"]["AND"] = build_tag_query_dict_tuple(tags)

    if registered_with:
        variables["hostFilter"]["NOT"] = {"insights_id": {"eq": None}}

    response = graphql_query(SYSTEM_PROFILE_QUERY, variables)

    print(f"response: {response}")

    data = response["hostSystemProfile"]

    check_pagination(offset, data["sap_sids"]["meta"]["total"])

    return flask_json_response(
        build_collection_response(data["sap_sids"], page, per_page, data["sap_sids"]["meta"]["total"])
    )

import re
from urllib.parse import quote_plus as url_quote

import flask

from api import api_operation
from api import build_collection_response
from api import flask_json_response
from api import metrics
from app.config import BulkQuerySource
from app.logging import get_logger
from app.utils import Tag
from app.xjoin import check_pagination
from app.xjoin import graphql_query
from app.xjoin import pagination_params

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


def is_enabled():
    return flask.current_app.config["INVENTORY_CONFIG"].bulk_query_source == BulkQuerySource.xjoin


@api_operation
@metrics.api_request_time.time()
def get_tags(search=None, tags=None, order_by=None, order_how=None, page=None, per_page=None):
    if not is_enabled():
        flask.abort(503)

    limit, offset = pagination_params(page, per_page)

    variables = {"order_by": order_by, "order_how": order_how, "limit": limit, "offset": offset}

    if search:
        variables["filter"] = {
            # Escaped to prevent ReDoS
            "name": f".*{re.escape(url_quote(search, safe=''))}.*"
        }

    if tags:
        variables["hostFilter"] = {"AND": [{"tag": Tag().from_string(tag).data()} for tag in tags]}

    response = graphql_query(TAGS_QUERY, variables)
    data = response["hostTags"]

    check_pagination(offset, data["meta"]["total"])

    return flask_json_response(build_collection_response(data["data"], page, per_page, data["meta"]["total"]))

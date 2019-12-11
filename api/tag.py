import re
from urllib.parse import quote_plus as url_quote

import flask
from flask import request
from requests import post

from api import api_operation
from api import metrics
from app.logging import get_logger
from app.utils import Tag

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
                count,
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


# TODO: reuse this function
def _get_forwarded_headers(headers):
    return {key: headers.get(key) for key in ["x-rh-identity", "x-rh-insights-request-id"]}


# TODO: reuse this function
def _pagination_params(page, per_page):
    limit = per_page
    offset = (page - 1) * per_page
    return limit, offset


def _build_response(data, page, per_page):
    return {
        "total": data["meta"]["total"],
        "count": data["meta"]["count"],
        "page": page,
        "per_page": per_page,
        "results": data["data"],
    }


@api_operation
@metrics.api_request_time.time()
def get_tags(search=None, tags=None, order_by=None, order_how=None, page=None, per_page=None):
    if False:  # TODO: check if XJOIN_GRAPHQL_URL is configured
        flask.abort(503)

    limit, offset = _pagination_params(page, per_page)

    variables = {"order_by": order_by, "order_how": order_how, "limit": limit, "offset": offset}

    if search:
        variables["filter"] = {
            # Escaped to prevent ReDoS
            "name": f".*{re.escape(url_quote(search, safe=''))}.*"
        }

    if tags:
        variables["hostFilter"] = {"AND": [{"tag": Tag().from_string(tag).data()} for tag in tags]}

    logger.debug("executing TAGS_QUERY, variables: %s", variables)
    payload = {"query": TAGS_QUERY, "variables": variables}

    headers = _get_forwarded_headers(request.headers)

    # TODO: reuse graphql client code
    # TODO: actual URL
    response = graphql_query("http://localhost:4000/graphql", payload, headers)
    data = response["data"]["hostTags"]

    if data["meta"]["total"] and offset >= data["meta"]["total"]:
        flask.abort(404, "Page number too high, no more tags.")

    return _build_response(data, page, per_page)


def graphql_query(url, payload, headers):
    response = post(url, json=payload, headers=headers)

    if response.status_code != 200:
        logger.error("TAGS_QUERY failed with %s", response.status_code)
        flask.abort(503, "GraphQL query failed.")

    return response.json()

from logging import getLogger

from flask import abort
from flask import current_app
from flask import request
from requests import post

from api.metrics import outbound_http_response_time
from app import IDENTITY_HEADER
from app import inventory_config
from app import REQUEST_ID_HEADER
from app import UNKNOWN_REQUEST_ID_VALUE
from app.culling import staleness_to_conditions

__all__ = ("graphql_query", "pagination_params", "staleness_filter", "string_contains", "string_contains_lc", "url")

logger = getLogger("graphql")
outbound_http_metric = outbound_http_response_time.labels("xjoin")


def check_pagination(offset, total):
    if total and offset >= total:
        abort(404)  # Analogous to flask_sqlalchemy.BaseQuery.paginate


def graphql_query(query_string, variables, failure_logger):
    url_ = url()
    logger.info("QUERY: URL %s; query %s, variables %s", url_, query_string, variables)
    payload = {"query": query_string, "variables": variables}

    with outbound_http_metric.time():
        response = post(url_, json=payload, headers=_forwarded_headers())

    status = response.status_code
    if status != 200:
        failure_logger(logger)
        logger.error("xjoin-search returned status: %s", status)
        abort(500, "Error, request could not be completed")

    logger.debug("QUERY: response %s", response.text)
    response_body = response.json()
    return response_body["data"]


def pagination_params(page, per_page):
    limit = per_page
    offset = (page - 1) * per_page
    return limit, offset


def hosts_order_by_params(order_by, order_how):
    if order_how and not order_by:
        raise ValueError(
            "Providing ordering direction without a column is not supported. "
            "Provide order_by={updated,display_name}."
        )

    if not order_by:
        order_by = "updated"
    if not order_how:
        order_how = "DESC"

    if order_by not in ["display_name", "updated"]:
        raise ValueError('Unsupported ordering column, use "updated" or "display_name".')
    if order_how not in ["ASC", "DESC"]:
        raise ValueError('Unsupported ordering direction, use "ASC" or "DESC".')

    if order_by == "updated":
        order_by = "modified_on"

    return order_by, order_how


def staleness_filter(staleness):
    config = inventory_config()
    return staleness_to_conditions(config, staleness, _stale_timestamp_filter)


def string_contains(string):
    return {"matches": f"*{string}*"}


def string_contains_lc(string):
    return {"matches_lc": f"*{string}*"}


def url():
    return current_app.config["INVENTORY_CONFIG"].xjoin_graphql_url


def _forwarded_headers():
    return {
        IDENTITY_HEADER: request.headers[IDENTITY_HEADER],
        REQUEST_ID_HEADER: request.headers.get(REQUEST_ID_HEADER, UNKNOWN_REQUEST_ID_VALUE),
    }


def _stale_timestamp_filter(gt=None, lte=None):
    filter_ = {}
    if gt:
        filter_["gt"] = gt.isoformat()
    if lte:
        filter_["lte"] = lte.isoformat()
    return {"stale_timestamp": filter_}

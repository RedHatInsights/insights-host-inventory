from logging import getLogger

from flask import abort
from flask import current_app
from flask import request
from requests import post

from api.metrics import outbound_http_response_time
from app import IDENTITY_HEADER
from app import inventory_config
from app import REQUEST_ID_HEADER
from app.culling import staleness_to_conditions

__all__ = (
    "graphql_query",
    "pagination_params",
    "staleness_filter",
    "string_contains",
    "string_contains_lc",
    "url",
    "params_to_order",
)

logger = getLogger("graphql")
outbound_http_metric = outbound_http_response_time.labels("xjoin")

ORDER_BY_MAPPING = {
    None: "modified_on",
    "updated": "modified_on",
    "display_name": "display_name",
    "operating_system": "operating_system",
}

GROUPS_ORDER_BY_MAPPING = {
    None: "group",
    "name": "group",
    "host_ids": "count",
}

ORDER_HOW_MAPPING = {"modified_on": "DESC", "display_name": "ASC", "operating_system": "DESC"}

GROUPS_ORDER_HOW_MAPPING = {"group": "DESC", "count": "DESC"}


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


def params_to_order(param_order_by, param_order_how):
    if param_order_how and not param_order_by:
        raise ValueError(
            "Providing ordering direction without a column is not supported. "
            "Provide order_by={updated,display_name}."
        )

    try:
        xjoin_order_by = ORDER_BY_MAPPING[param_order_by]
    except KeyError:
        raise ValueError(f'Unsupported ordering column: can not order by "{param_order_by}"')

    try:
        xjoin_order_how = param_order_how or ORDER_HOW_MAPPING[xjoin_order_by]
    except KeyError:
        raise ValueError(f'Unsupported ordering direction "{param_order_how}": use "ASC" or "DESC".')

    return xjoin_order_by, xjoin_order_how


def groups_params_to_order(param_order_by, param_order_how):
    if param_order_how and not param_order_by:
        raise ValueError("Providing ordering direction without a column is not supported. ")

    try:
        xjoin_order_by = GROUPS_ORDER_BY_MAPPING[param_order_by]
    except KeyError:
        raise ValueError(f'Unsupported ordering column: can not order by "{param_order_by}"')

    try:
        xjoin_order_how = param_order_how or GROUPS_ORDER_HOW_MAPPING[xjoin_order_by]
    except KeyError:
        raise ValueError(f'Unsupported ordering direction "{param_order_how}": use "ASC" or "DESC".')

    return xjoin_order_by, xjoin_order_how


def staleness_filter(staleness):
    config = inventory_config()
    staleness_conditions = tuple(staleness_to_conditions(config, staleness, _stale_timestamp_filter))
    if "unknown" in staleness:
        staleness_conditions += ({"stale_timestamp": {"eq": None}},)
    return staleness_conditions


def string_contains(string):
    return {"matches": f"*{string}*"}


def string_contains_lc(string):
    return {"matches_lc": f"*{string}*"}


def url():
    return current_app.config["INVENTORY_CONFIG"].xjoin_graphql_url


def _forwarded_headers():
    return {
        IDENTITY_HEADER: request.headers[IDENTITY_HEADER],
        REQUEST_ID_HEADER: request.headers.get(REQUEST_ID_HEADER),
    }


def _stale_timestamp_filter(gt=None, lte=None):
    filter_ = {}
    if gt:
        filter_["gt"] = gt.isoformat()
    if lte:
        filter_["lte"] = lte.isoformat()
    return {"stale_timestamp": filter_}

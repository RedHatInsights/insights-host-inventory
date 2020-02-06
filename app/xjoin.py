from logging import getLogger

from flask import abort
from flask import current_app
from flask import request
from requests import post

from app import IDENTITY_HEADER
from app import inventory_config
from app import REQUEST_ID_HEADER
from app import UNKNOWN_REQUEST_ID_VALUE
from app.culling import staleness_to_conditions

__all__ = ("graphql_query", "pagination_params", "staleness_filter", "string_contains", "url")

logger = getLogger("graphql")


def check_pagination(offset, total):
    if total and offset >= total:
        abort(404)  # Analogous to flask_sqlalchemy.BaseQuery.paginate


def graphql_query(query_string, variables):
    url_ = url()
    logger.info("QUERY: URL %s; query %s, variables %s", url_, query_string, variables)
    payload = {"query": query_string, "variables": variables}

    response = post(url_, json=payload, headers=_forwarded_headers())
    status = response.status_code
    if status != 200:
        logger.error("xjoin-search returned status: %s", status)
        abort(500, "Error, request could not be completed")

    logger.debug("QUERY: response %s", response.text)
    response_body = response.json()
    return response_body["data"]


def pagination_params(page, per_page):
    limit = per_page
    offset = (page - 1) * per_page
    return limit, offset


def staleness_filter(staleness):
    config = inventory_config()
    return staleness_to_conditions(config, staleness, _stale_timestamp_filter)


def string_contains(string):
    return f"*{string}*"


def url():
    return current_app.config["INVENTORY_CONFIG"].xjoin_graphql_url


def _forwarded_headers():
    return {
        IDENTITY_HEADER: request.headers[IDENTITY_HEADER],
        REQUEST_ID_HEADER: request.headers.get(REQUEST_ID_HEADER, UNKNOWN_REQUEST_ID_VALUE),
    }


def _stale_timestamp_filter(gte=None, lte=None):
    filter_ = {}
    if gte:
        filter_["gte"] = gte.isoformat()
    if lte:
        filter_["lte"] = lte.isoformat()
    return {"stale_timestamp": filter_}

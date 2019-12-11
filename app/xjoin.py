from logging import getLogger

from flask import abort
from flask import current_app
from requests import post

from app.auth import authenticated_request

__all__ = ("graphql_query", "pagination_params", "string_contains", "url")

logger = getLogger("graphql")


def check_pagination(offset, total):
    if total and offset >= total:
        abort(404)  # Analogous to flask_sqlalchemy.BaseQuery.paginate


def graphql_query(query_string, variables):
    url_ = url()
    logger.info("QUERY: URL %s; query %s, variables %s", url_, query_string, variables)
    payload = {"query": query_string, "variables": variables}

    response = authenticated_request(post, url_, json=payload)
    logger.info("QUERY: response %s", response.text)
    response_body = response.json()
    return response_body["data"]


def pagination_params(page, per_page):
    limit = per_page
    offset = (page - 1) * per_page
    return limit, offset


def string_contains(string):
    return f"*{string}*"


def url():
    return current_app.config["INVENTORY_CONFIG"].xjoin_graphql_url

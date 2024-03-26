from functools import partial
from logging import getLogger

from flask import abort
from flask import current_app
from flask import request
from requests import post

from api.metrics import outbound_http_response_time
from api.staleness_query import get_staleness_obj
from app import IDENTITY_HEADER
from app import REQUEST_ID_HEADER
from app.config import HOST_TYPES
from app.culling import staleness_to_conditions
from app.models import OLD_TO_NEW_REPORTER_MAP
from app.serialization import serialize_staleness_to_dict

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
    "group_name": "group_name",
    "operating_system": "operating_system",
}

ORDER_HOW_MAPPING = {"modified_on": "DESC", "display_name": "ASC", "group_name": "ASC", "operating_system": "DESC"}


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


def staleness_filter(staleness):
    staleness_obj = serialize_staleness_to_dict(get_staleness_obj())
    staleness_conditions = tuple()
    for host_type in HOST_TYPES:
        staleness_conditions += tuple(
            staleness_to_conditions(staleness_obj, staleness, host_type, _stale_timestamp_filter)
        )
    return staleness_conditions


def per_reporter_staleness_filter(staleness, reporter):
    staleness_obj = serialize_staleness_to_dict(get_staleness_obj())
    staleness_conditions = tuple()
    for host_type in HOST_TYPES:
        staleness_conditions += tuple(
            staleness_to_conditions(
                staleness_obj, staleness, host_type, partial(_stale_timestamp_per_reporter_filter, reporter=reporter)
            )
        )
    return staleness_conditions


def string_contains(string):
    return {"matches": f"*{string}*"}


def string_contains_lc(string):
    return {"matches_lc": f"*{string}*"}


def string_exact_lc(string):
    return {"eq_lc": string}


def url():
    return current_app.config["INVENTORY_CONFIG"].xjoin_graphql_url


def _forwarded_headers():
    return {
        IDENTITY_HEADER: request.headers[IDENTITY_HEADER],
        REQUEST_ID_HEADER: request.headers.get(REQUEST_ID_HEADER),
    }


def _stale_timestamp_filter(gt=None, lte=None, host_type=None):
    filter_ = {}
    if gt:
        filter_["gt"] = gt.isoformat()
    if lte:
        filter_["lte"] = lte.isoformat()
    return {"AND": ({"modified_on": filter_, "spf_host_type": {"eq": host_type}})}


def _stale_timestamp_per_reporter_filter(gt=None, lte=None, host_type=None, reporter=None):
    filter_ = {}
    if gt:
        filter_["gt"] = gt.isoformat()
    if lte:
        filter_["lte"] = lte.isoformat()

    # When filtering on old reporter name, include the names of the
    # new reporters associated with the old reporter.
    non_negative_reporter = reporter.replace("!", "")
    reporter_list = [non_negative_reporter]
    if non_negative_reporter in OLD_TO_NEW_REPORTER_MAP.keys():
        reporter_list.extend(OLD_TO_NEW_REPORTER_MAP[non_negative_reporter])

    if reporter.startswith("!"):
        return {
            "AND": [
                {"spf_host_type": {"eq": host_type}},
                {
                    "AND": [
                        {
                            "NOT": {
                                "per_reporter_staleness": {"reporter": {"eq": rep.replace("!", "")}},
                            }
                        }
                        for rep in reporter_list
                    ]
                },
                {"modified_on": filter_},
            ]
        }
    else:
        return {
            "AND": [
                {"spf_host_type": {"eq": host_type}},
                {
                    "OR": [
                        {
                            "per_reporter_staleness": {
                                "reporter": {"eq": rep},
                                "last_check_in": filter_,
                            }
                        }
                        for rep in reporter_list
                    ]
                },
            ]
        }

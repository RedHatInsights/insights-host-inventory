import re

import flask

from api import api_operation
from api import build_collection_response
from api import flask_json_response
from api import metrics
from api.host import get_bulk_query_source
from api.host_query_xjoin import build_sap_sids_filter
from api.host_query_xjoin import build_sap_system_filters
from api.host_query_xjoin import build_tag_query_dict_tuple
from app import Permission
from app.config import BulkQuerySource
from app.instrumentation import log_get_sap_sids_failed
from app.instrumentation import log_get_sap_sids_succeded
from app.instrumentation import log_get_sap_system_failed
from app.instrumentation import log_get_sap_system_succeded
from app.logging import get_logger
from app.xjoin import check_pagination
from app.xjoin import graphql_query
from app.xjoin import pagination_params
from app.xjoin import staleness_filter
from lib.middleware import rbac

logger = get_logger(__name__)


SAP_SYSTEM_QUERY = """
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

SAP_SIDS_QUERY = """
    query hostSystemProfile (
        $hostFilter: HostFilter
        $filter: SapSidFilter
    ) {
        hostSystemProfile (
            hostFilter: $hostFilter
        ) {
            sap_sids (
                filter: $filter
            ) {
                meta {
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
def get_sap_system(tags=None, page=None, per_page=None, staleness=None, registered_with=None, filter=None):
    if not xjoin_enabled():
        flask.abort(503)

    limit, offset = pagination_params(page, per_page)

    variables = {
        "hostFilter": {
            # we're not indexing null timestamps in ES
            "OR": list(staleness_filter(staleness))
        }
    }
    hostfilter_and_variables = ()

    if tags:
        hostfilter_and_variables = build_tag_query_dict_tuple(tags)

    if registered_with:
        variables["hostFilter"]["NOT"] = {"insights_id": {"eq": None}}

    if filter:
        if filter.get("system_profile"):
            if filter["system_profile"].get("sap_system"):
                hostfilter_and_variables += build_sap_system_filters(filter["system_profile"].get("sap_system"))
            if filter["system_profile"].get("sap_sids"):
                hostfilter_and_variables += build_sap_sids_filter(filter["system_profile"]["sap_sids"])

    if hostfilter_and_variables != ():
        variables["hostFilter"]["AND"] = hostfilter_and_variables

    response = graphql_query(SAP_SYSTEM_QUERY, variables, log_get_sap_system_failed)

    data = response["hostSystemProfile"]

    check_pagination(offset, data["sap_system"]["meta"]["total"])

    log_get_sap_system_succeded(logger, data)
    return flask_json_response(
        build_collection_response(data["sap_system"]["data"], page, per_page, data["sap_system"]["meta"]["total"])
    )


@api_operation
@rbac(Permission.READ)
@metrics.api_request_time.time()
def get_sap_sids(search=None, tags=None, page=None, per_page=None, staleness=None, registered_with=None, filter=None):
    if not xjoin_enabled():
        flask.abort(503)

    limit, offset = pagination_params(page, per_page)

    variables = {
        "hostFilter": {
            # we're not indexing null timestamps in ES
            "OR": list(staleness_filter(staleness))
        }
    }

    hostfilter_and_variables = ()

    if tags:
        hostfilter_and_variables = build_tag_query_dict_tuple(tags)

    if registered_with:
        variables["hostFilter"]["NOT"] = {"insights_id": {"eq": None}}

    if search:
        variables["filter"] = {
            # Escaped so that the string literals are not interpreted as regex
            "search": {"regex": f".*{re.escape(search)}.*"}
        }

    if filter:
        if filter.get("system_profile"):
            if filter["system_profile"].get("sap_system"):
                hostfilter_and_variables += build_sap_system_filters(filter["system_profile"].get("sap_system"))
            if filter["system_profile"].get("sap_sids"):
                hostfilter_and_variables += build_sap_sids_filter(filter["system_profile"]["sap_sids"])

    if hostfilter_and_variables != ():
        variables["hostFilter"]["AND"] = hostfilter_and_variables

    response = graphql_query(SAP_SIDS_QUERY, variables, log_get_sap_sids_failed)

    data = response["hostSystemProfile"]

    check_pagination(offset, data["sap_sids"]["meta"]["total"])

    log_get_sap_sids_succeded(logger, data)
    return flask_json_response(
        build_collection_response(data["sap_sids"]["data"], page, per_page, data["sap_sids"]["meta"]["total"])
    )

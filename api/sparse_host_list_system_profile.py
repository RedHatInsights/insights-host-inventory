import flask

from api.filtering.filtering import host_id_list_query_filter
from app.instrumentation import log_get_sparse_system_profile_failed
from app.instrumentation import log_get_sparse_system_profile_succeeded
from app.logging import get_logger
from app.serialization import serialize_host_system_profile_xjoin
from app.xjoin import check_pagination
from app.xjoin import graphql_query
from app.xjoin import pagination_params
from app.xjoin import params_to_order


logger = get_logger(__name__)

SYSTEM_PROFILE_SPARSE_QUERY = """
    query hosts(
        $hostFilter: [HostFilter!],
        $fields: [String!],
        $limit: Int,
        $offset: Int,
        $order_by: HOSTS_ORDER_BY,
        $order_how: ORDER_DIR,
    ){
        hosts (
            filter:{
                AND:$hostFilter
            },
            limit: $limit,
            offset: $offset,
            order_by: $order_by,
            order_how: $order_how
        ) {
            meta { count, total }
            data {
                id
                system_profile_facts (filter: $fields)
            }
        }
    }
"""

SYSTEM_PROFILE_FULL_QUERY = """
    query hosts(
        $hostFilter: [HostFilter!],
        $limit: Int,
        $offset: Int,
        $order_by: HOSTS_ORDER_BY,
        $order_how: ORDER_DIR,
    ){
        hosts (
            filter:{
                AND:$hostFilter
            },
            limit: $limit,
            offset: $offset,
            order_by: $order_by,
            order_how: $order_how
        ) {
            meta { count, total }
            data {
                id
                system_profile_facts
            }
        }
    }
"""


def get_sparse_system_profile(host_id_list, page, per_page, order_by, order_how, fields, rbac_filter):
    limit, offset = pagination_params(page, per_page)

    try:
        order_by, order_how = params_to_order(order_by, order_how)
    except ValueError as e:
        flask.abort(400, str(e))

    host_filter = host_id_list_query_filter(host_id_list, rbac_filter)

    sp_query = SYSTEM_PROFILE_FULL_QUERY
    variables = {
        "hostFilter": host_filter,
        "limit": limit,
        "offset": offset,
        "order_by": order_by,
        "order_how": order_how,
    }

    if fields.get("system_profile"):
        variables["fields"] = list(fields.get("system_profile").keys())
        sp_query = SYSTEM_PROFILE_SPARSE_QUERY

    response = graphql_query(sp_query, variables, log_get_sparse_system_profile_failed)
    response_data = response["hosts"]
    check_pagination(offset, response_data["meta"]["total"])

    total = response_data["meta"]["total"]
    response_list = [serialize_host_system_profile_xjoin(host_data) for host_data in response_data["data"]]
    log_get_sparse_system_profile_succeeded(logger, response_data)

    return total, response_list

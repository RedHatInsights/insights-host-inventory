import flask
from flask_api import status

from app.instrumentation import log_get_sparse_system_profile_failed
from app.instrumentation import log_get_sparse_system_profile_succeeded
from app.logging import get_logger
from app.serialization import serialize_host_system_profile_xjoin
from app.xjoin import check_pagination
from app.xjoin import graphql_query
from app.xjoin import hosts_order_by_params
from app.xjoin import pagination_params


logger = get_logger(__name__)

SYSTEM_PROFILE_QUERY = """
    query hosts(
        $host_ids: [HostFilter!],
        $fields: [String!],
        $limit: Int,
        $offset: Int,
        $order_by: HOSTS_ORDER_BY,
        $order_how: ORDER_DIR,
    ){
        hosts (
            filter:{
                OR:$host_ids
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


def get_sparse_system_profile(host_id_list, page, per_page, order_by, order_how, fields):
    if not fields.get("system_profile"):
        flask.abort(400, status.HTTP_400_BAD_REQUEST)

    limit, offset = pagination_params(page, per_page)

    try:
        order_by, order_how = hosts_order_by_params(order_by, order_how)
    except ValueError as e:
        flask.abort(400, str(e))

    host_ids = [{"id": {"eq": host_id}} for host_id in host_id_list]
    system_profile_fields = list(fields.get("system_profile").keys())
    if len(system_profile_fields) > 0:
        variables = {
            "host_ids": host_ids,
            "fields": system_profile_fields,
            "limit": limit,
            "offset": offset,
            "order_by": order_by,
            "order_how": order_how,
        }
        response = graphql_query(SYSTEM_PROFILE_QUERY, variables, log_get_sparse_system_profile_failed)

        response_data = response["hosts"]

        check_pagination(offset, response_data["meta"]["total"])

        total = response_data["meta"]["total"]

        response_list = [serialize_host_system_profile_xjoin(host_data) for host_data in response_data["data"]]

        log_get_sparse_system_profile_succeeded(logger, response_data)

    return total, response_list

import flask

from api import api_operation
from api import build_collection_response
from api import flask_json_response
from api import metrics
from api.host import get_bulk_query_source
from api.host import get_host_list_by_id_list
from api.host_query_db import params_to_order_by
from app import Permission
from app.config import BulkQuerySource
from app.instrumentation import log_get_sparse_system_profile_failed
from app.instrumentation import log_get_sparse_system_profile_succeeded
from app.logging import get_logger
from app.serialization import serialize_host_system_profile
from app.serialization import serialize_host_system_profile_xjoin
from app.xjoin import check_pagination
from app.xjoin import graphql_query
from app.xjoin import hosts_order_by_params
from app.xjoin import pagination_params
from lib.middleware import rbac


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


def xjoin_enabled():
    return get_bulk_query_source() == BulkQuerySource.xjoin


@api_operation
@rbac(Permission.READ)
@metrics.api_request_time.time()
def get_host_system_profile_by_id(host_id_list, page=1, per_page=100, order_by=None, order_how=None, fields=None):
    if fields:
        if not xjoin_enabled():
            flask.abort(503)

        limit, offset = pagination_params(page, per_page)

        try:
            order_by, order_how = hosts_order_by_params(order_by, order_how)
        except ValueError as e:
            flask.abort(400, str(e))

        if fields.get("system_profile"):
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
    else:
        query = get_host_list_by_id_list(host_id_list)
        try:
            order_by = params_to_order_by(order_by, order_how)
        except ValueError as e:
            flask.abort(400, str(e))
        else:
            query = query.order_by(*order_by)
        query_results = query.paginate(page, per_page, True)

        total = query_results.total

        response_list = [serialize_host_system_profile(host) for host in query_results.items]

    json_output = build_collection_response(response_list, page, per_page, total)
    return flask_json_response(json_output)

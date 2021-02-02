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
from app.serialization import serialize_host_system_profile
from lib.middleware import rbac

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
                display_name
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
        # if fields.get("system_profile"):
            
    query = get_host_list_by_id_list(host_id_list)
    print('Host List from system_profile_host_list', host_id_list)
    print('fields', fields)
    try:
        order_by = params_to_order_by(order_by, order_how)
    except ValueError as e:
        flask.abort(400, str(e))
    else:
        query = query.order_by(*order_by)
    query_results = query.paginate(page, per_page, True)

    response_list = [serialize_host_system_profile(host) for host in query_results.items]
    json_output = build_collection_response(response_list, page, per_page, query_results.total)
    return flask_json_response(json_output)


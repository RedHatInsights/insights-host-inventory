import flask
from flask import Response
from flask_api import status

from api import api_operation
from api import flask_json_response
from api import metrics
from api.group_query import get_filtered_group_list_db
from api.resource_query import build_paginated_resource_list_response
from api.resource_query import get_resources_types
from app import RbacPermission
from app import RbacResourceType
from app.instrumentation import log_get_group_list_failed
from app.instrumentation import log_get_group_list_succeeded
from app.instrumentation import log_get_resource_type_list_failed
from app.instrumentation import log_get_resource_type_list_succeeded
from app.logging import get_logger
from app.serialization import serialize_group
from lib.feature_flags import FLAG_INVENTORY_GROUPS
from lib.feature_flags import get_flag_value
from lib.middleware import rbac
from lib.middleware import RbacFilter

logger = get_logger(__name__)


@api_operation
@rbac(RbacResourceType.ALL, RbacPermission.ADMIN, "rbac")
@metrics.api_request_time.time()
def get_resource_type_list(page=1, per_page=10, rbac_filter: RbacFilter = RbacFilter()):
    if not get_flag_value(FLAG_INVENTORY_GROUPS):
        return Response(None, status.HTTP_501_NOT_IMPLEMENTED)

    try:
        resource_list, total = get_resources_types()
        log_get_resource_type_list_succeeded(logger, resource_list)
    except ValueError as e:
        log_get_resource_type_list_failed(logger)
        flask.abort(400, str(e))

    return flask_json_response(
        build_paginated_resource_list_response(total, page, per_page, resource_list, "/inventory/v1/resource-types")
    )


@api_operation
@rbac(RbacResourceType.ALL, RbacPermission.ADMIN, "rbac")
@metrics.api_request_time.time()
def get_resource_type_groups_list(
    name=None,
    page=1,
    per_page=100,
    order_by=None,
    order_how=None,
    rbac_filter: RbacFilter = RbacFilter(),
):
    if not get_flag_value(FLAG_INVENTORY_GROUPS):
        return Response(None, status.HTTP_501_NOT_IMPLEMENTED)

    try:
        group_list, total = get_filtered_group_list_db(name, page, per_page, order_by, order_how, rbac_filter)
    except ValueError as e:
        log_get_group_list_failed(logger)
        flask.abort(400, str(e))

    log_get_group_list_succeeded(logger, group_list)

    return flask_json_response(
        build_paginated_resource_list_response(total, page, per_page, [serialize_group(group) for group in group_list])
    )

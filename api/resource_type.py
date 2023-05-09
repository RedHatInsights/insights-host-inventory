import flask
from flask import Response
from flask_api import status

from api import api_operation
from api import flask_json_response
from api import metrics
from api.group_query import get_filtered_group_list_db
from api.resource_query import build_paginated_resource_list_response
from api.resource_query import get_resources_types
from app import Permission
from app.instrumentation import log_get_group_list_failed
from app.instrumentation import log_get_group_list_succeeded
from app.instrumentation import log_get_resource_type_list_failed
from app.instrumentation import log_get_resource_type_list_succeeded
from app.logging import get_logger
from lib.feature_flags import FLAG_INVENTORY_GROUPS
from lib.feature_flags import get_flag_value
from lib.middleware import rbac

logger = get_logger(__name__)


@api_operation
@rbac(Permission.ADMIN)
@metrics.api_request_time.time()
def get_resource_type_list(
    page=1,
    per_page=100,
):
    if not get_flag_value(FLAG_INVENTORY_GROUPS):
        return Response(None, status.HTTP_501_NOT_IMPLEMENTED)

    try:
        resource_list, total = get_resources_types()
        log_get_resource_type_list_succeeded(logger, resource_list)
    except ValueError as e:
        log_get_resource_type_list_failed(logger)
        flask.abort(400, str(e))

    return flask_json_response(build_paginated_resource_list_response(total, page, per_page, resource_list))


@api_operation
@rbac(Permission.ADMIN)
@metrics.api_request_time.time()
def get_resource_type_groups_list(
    page=1,
    per_page=100,
    order_by=None,
    order_how=None,
):
    if not get_flag_value(FLAG_INVENTORY_GROUPS):
        return Response(None, status.HTTP_501_NOT_IMPLEMENTED)

    try:
        group_list, total = get_filtered_group_list_db(None, page, per_page, order_by, order_how)
    except ValueError as e:
        log_get_group_list_failed(logger)
        flask.abort(400, str(e))

    log_get_group_list_succeeded(logger, group_list)

    return flask_json_response(
        build_paginated_resource_list_response(
            total, page, per_page, [{"value": str(group.id)} for group in group_list]
        )
    )

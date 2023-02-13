import flask
from flask import current_app
from flask_api import status

from api import api_operation
from api import flask_json_response
from api import metrics
from api.resource_query import build_paginated_resource_list_response
from app import Permission
from lib.feature_flags import FLAG_INVENTORY_GROUPS
from lib.feature_flags import get_flag_value
from lib.middleware import rbac


@api_operation
@rbac(Permission.ADMIN)
@metrics.api_request_time.time()
def get_resource_type_list(
    page=1,
    per_page=100,
    order_by=None,
    order_how=None,
    filter=None,
):
    try:
        resource_list = get_resource_type_list()
    except ValueError as e:
        log_get_resource_type_list_failed(logger)
        flask.abort(400, str(e))

    return flask_json_response(
        build_paginated_resource_list_response(total, page, per_page, resource_list, additional_fields)
    )

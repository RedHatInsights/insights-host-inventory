import flask

from api import api_operation
from api import flask_json_response
from api import metrics
from api.group_query import get_filtered_group_list_db
from api.resource_query import build_paginated_resource_list_response
from api.resource_query import get_resources_types
from app.auth import get_current_identity
from app.auth.rbac import RbacPermission
from app.auth.rbac import RbacResourceType
from app.instrumentation import log_get_group_list_failed
from app.instrumentation import log_get_group_list_succeeded
from app.instrumentation import log_get_resource_type_list_failed
from app.instrumentation import log_get_resource_type_list_succeeded
from app.logging import get_logger
from lib.group_repository import serialize_group
from lib.middleware import rbac

logger = get_logger(__name__)


@api_operation
@rbac(RbacResourceType.ALL, RbacPermission.ADMIN, "rbac")
@metrics.api_request_time.time()
def get_resource_type_list(
    page=1,
    per_page=10,
):
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
    rbac_filter=None,
):
    try:
        group_list, total = get_filtered_group_list_db(
            name,
            page,
            per_page,
            order_by,
            order_how,
            rbac_filter,
            "standard",
        )
    except ValueError as e:
        log_get_group_list_failed(logger)
        flask.abort(400, str(e))

    log_get_group_list_succeeded(logger, group_list)
    org_id = get_current_identity().org_id
    serialized_groups = [serialize_group(group, org_id) for group in group_list]
    return flask_json_response(build_paginated_resource_list_response(total, page, per_page, serialized_groups))

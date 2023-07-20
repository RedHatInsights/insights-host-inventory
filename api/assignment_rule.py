from flask import abort
from flask import Response
from flask_api import status

from api import api_operation
from api import flask_json_response
from api import metrics
from api.assignment_rule_query import build_paginated_assignmentrule_list_response
from api.assignment_rule_query import get_filtered_assignment_rule_list_db
from app import RbacPermission
from app import RbacResourceType
from app.instrumentation import log_get_assignment_rules_list_succeeded
from app.instrumentation import log_get_group_list_failed
from app.logging import get_logger
from lib.feature_flags import FLAG_INVENTORY_ASSIGNMENT_RULES
from lib.feature_flags import get_flag_value
from lib.middleware import rbac


logger = get_logger(__name__)


@api_operation
@rbac(RbacResourceType.GROUPS, RbacPermission.READ)
@metrics.api_request_time.time()
def get_assignment_rule_list(
    name=None,
    page=1,
    per_page=100,
    order_by=None,
    order_how=None,
    rbac_filter=None,
):
    if not get_flag_value(FLAG_INVENTORY_ASSIGNMENT_RULES):
        return Response(None, status.HTTP_501_NOT_IMPLEMENTED)

    try:
        rule_list, total = get_filtered_assignment_rule_list_db(name, page, per_page, order_by, order_how, rbac_filter)
    except ValueError as e:
        log_get_group_list_failed(logger)
        abort(status.HTTP_400_BAD_REQUEST, str(e))

    log_get_assignment_rules_list_succeeded(logger, rule_list)

    return flask_json_response(
        build_paginated_assignmentrule_list_response(total, page, per_page, rule_list),
        status.HTTP_200_OK,
    )


@api_operation
@rbac(RbacResourceType.GROUPS, RbacPermission.WRITE)
@metrics.api_request_time.time()
def create_assignment_rule(body, rbac_filter=None):
    return True


@api_operation
@rbac(RbacResourceType.GROUPS, RbacPermission.WRITE)
@metrics.api_request_time.time()
def patch_assignment_rule_by_id(assignment_rule_id, body, rbac_filter=None):
    return True


@api_operation
@rbac(RbacResourceType.GROUPS, RbacPermission.WRITE)
@metrics.api_request_time.time()
def delete_assignment_rules(assignment_rule_id_list, rbac_filter=None):
    return True


@api_operation
@rbac(RbacResourceType.GROUPS, RbacPermission.READ)
@metrics.api_request_time.time()
def get_assignment_rules_by_id(
    assignment_rule_id_list,
    page=1,
    per_page=100,
    order_by=None,
    order_how=None,
    rbac_filter=None,
):
    return True


@api_operation
@rbac(RbacResourceType.GROUPS, RbacPermission.WRITE)
@metrics.api_request_time.time()
def delete_hosts_from_assignment_rule(assignment_rule_id, host_id_list, rbac_filter=None):
    return True

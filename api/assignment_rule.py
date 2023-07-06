from flask import abort
from flask import current_app
from flask import Response
from flask_api import status
from marshmallow import ValidationError
from sqlalchemy.exc import IntegrityError

from api import api_operation
from api import flask_json_response
from api import metrics
from api.assignment_rule_query import get_filtered_assignment_rule_list_db
from api.group_query import build_group_response
from api.group_query import build_paginated_group_list_response
from api.group_query import get_filtered_group_list_db
from api.group_query import get_group_list_by_id_list_db
from app import RbacPermission
from app import RbacResourceType
from app.exceptions import InventoryException
from app.instrumentation import log_create_group_failed
from app.instrumentation import log_create_group_succeeded
from app.instrumentation import log_get_group_list_failed
from app.instrumentation import log_get_group_list_succeeded
from app.instrumentation import log_patch_group_failed
from app.instrumentation import log_patch_group_success
from app.logging import get_logger
from app.models import InputGroupSchema
from lib.feature_flags import FLAG_INVENTORY_ASSIGNMENT_RULE, FLAG_INVENTORY_GROUPS
from lib.feature_flags import get_flag_value
from lib.group_repository import add_group
from lib.group_repository import delete_group_list
from lib.group_repository import get_group_by_id_from_db
from lib.group_repository import patch_group
from lib.group_repository import remove_hosts_from_group
from lib.metrics import create_group_count
from lib.middleware import rbac
from lib.middleware import rbac_group_id_check

logger = get_logger(__name__)

# TODO: hbi.group-assignment-rule from Rich Oliveri
# what paramters as input?
# does it need its feature flag?
@api_operation
@rbac(RbacResourceType.GROUPS, RbacPermission.READ)
@metrics.api_request_time.time()
def get_assignment_rule_list(
    enabled=True, # check for this default value.
    name=None,
    filter=None,
    created_on=None,
    modified_on=None,
    page=1,
    per_page=100,
    order_by=None,
    order_how=None,
    rbac_filter=None,
):
    if not get_flag_value(FLAG_INVENTORY_ASSIGNMENT_RULE):
        return Response(None, status.HTTP_501_NOT_IMPLEMENTED)

    try:
        group_list, total = get_filtered_assignment_rule_list_db(name, page, per_page, order_by, order_how, rbac_filter)
    except ValueError as e:
        log_get_group_list_failed(logger)
        abort(400, str(e))

    log_get_group_list_succeeded(logger, group_list)

    return flask_json_response(build_paginated_group_list_response(total, page, per_page, group_list))


@api_operation
@rbac(RbacResourceType.GROUPS, RbacPermission.WRITE)
@metrics.api_request_time.time()
def create_assignment_rule(body, rbac_filter=None):
    return True


@api_operation
@rbac(RbacResourceType.GROUPS, RbacPermission.WRITE)
@metrics.api_request_time.time()
def patch_assignment_rule_by_id(group_id, body, rbac_filter=None):
    return True

@api_operation
@rbac(RbacResourceType.GROUPS, RbacPermission.WRITE)
@metrics.api_request_time.time()
def delete_assignment_rules(group_id_list, rbac_filter=None):
    return True


@api_operation
@rbac(RbacResourceType.GROUPS, RbacPermission.READ)
@metrics.api_request_time.time()
def get_assignment_rules_by_id(
    group_id_list,
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


def _error_json_response(title, detail, status=status.HTTP_400_BAD_REQUEST):
    return True

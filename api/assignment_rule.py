from flask import abort
from flask import Response
from flask_api import status
from marshmallow import ValidationError
from sqlalchemy.exc import IntegrityError

from api import api_operation
from api import error_json_response
from api import flask_json_response
from api import metrics
from api.assignment_rule_query import add_assignment_rule
from api.assignment_rule_query import build_paginated_assignmentrule_list_response
from api.assignment_rule_query import get_filtered_assignment_rule_list_db
from app import RbacPermission
from app import RbacResourceType
from app.instrumentation import log_get_assignment_rules_list_succeeded
from app.instrumentation import log_get_group_list_failed
from app.logging import get_logger
from app.models import InputAssignmentRule
from lib.feature_flags import FLAG_INVENTORY_ASSIGNMENT_RULES
from lib.feature_flags import get_flag_value
from lib.middleware import rbac


logger = get_logger(__name__)


# TODO: hbi.group-assignment-rule from Rich Oliveri
#   1. what paramters as input?
#   2. does it need its feature flag?
#   3. Rename the function to "get_assignment_rules"
@api_operation
@rbac(RbacResourceType.GROUPS, RbacPermission.READ)
@metrics.api_request_time.time()
def get_assignment_rule_list(
    enabled=True,  # check for this default value.
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
    if not get_flag_value(FLAG_INVENTORY_ASSIGNMENT_RULES):
        return Response(None, status.HTTP_501_NOT_IMPLEMENTED)

    try:
        # TODO: is rbac_filter needed
        rule_list, total = get_filtered_assignment_rule_list_db(name, page, per_page, order_by, order_how, rbac_filter)
    except ValueError as e:
        log_get_group_list_failed(logger)
        abort(400, str(e))

    log_get_assignment_rules_list_succeeded(logger, rule_list)

    return flask_json_response(build_paginated_assignmentrule_list_response(total, page, per_page, rule_list))


@api_operation
@rbac(RbacResourceType.GROUPS, RbacPermission.WRITE)
@metrics.api_request_time.time()
def create_assignment_rule(body, rbac_filter=None):
    # return True
    try:
        validated_create_assignment_rule = InputAssignmentRule().load(body)
    except ValidationError as e:
        logger.exception(f"Input validation error while creating assignment rule: {body}")
        return error_json_response("Validation Error", str(e.messages))

    try:
        created_assignment_rule = add_assignment_rule(validated_create_assignment_rule)
    except IntegrityError as error:
        group_id = validated_create_assignment_rule.get("group_id")
        name = validated_create_assignment_rule.get("name")
        if group_id in str(error.args):
            error_message = f"Group with UUID {group_id} does not exists."
            response_status = status.HTTP_404_NOT_FOUND
        if name in str(error.args):
            error_message = f"A assignment rule with name {name} alredy exists."
            response_status = status.HTTP_403_FORBIDDEN
        return error_json_response("Integrity error", str(error_message), response_status)

    return flask_json_response(created_assignment_rule, status.HTTP_201_CREATED)


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

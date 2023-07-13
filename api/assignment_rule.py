from flask import Response
from flask_api import status
from marshmallow import ValidationError
from sqlalchemy.exc import IntegrityError

from api import api_operation
from api import flask_json_response
from api import json_error_response
from api import metrics
from app import RbacPermission
from app import RbacResourceType
from app.instrumentation import log_post_assignment_rule_failed
from app.instrumentation import log_post_assignment_rule_succeeded
from app.logging import get_logger
from app.models import InputAssignmentRule
from app.serialization import serialize_assignment_rule
from lib.assignment_rule_repository import add_assignment_rule
from lib.feature_flags import FLAG_INVENTORY_ASSIGNMENT_RULES
from lib.feature_flags import get_flag_value
from lib.middleware import rbac


logger = get_logger(__name__)


@api_operation
@rbac(RbacResourceType.GROUPS, RbacPermission.WRITE)
@metrics.api_request_time.time()
def create_assignment_rule(body, rbac_filter=None):
    if not get_flag_value(FLAG_INVENTORY_ASSIGNMENT_RULES):
        return Response(None, status.HTTP_501_NOT_IMPLEMENTED)

    try:
        validated_create_assignment_rule = InputAssignmentRule().load(body)
    except ValidationError as e:
        logger.exception(f"Input validation error while creating assignment rule: {body}")
        log_post_assignment_rule_failed(logger)
        return json_error_response("Validation Error", str(e.messages), status.HTTP_400_BAD_REQUEST)

    try:
        created_assignment_rule = add_assignment_rule(validated_create_assignment_rule)
        created_assignment_rule = serialize_assignment_rule(created_assignment_rule)
    except IntegrityError as error:
        group_id = validated_create_assignment_rule.get("group_id")
        if group_id in str(error.args):
            if "ForeignKeyViolation" in str(error.args):
                error_message = f"Group with UUID {group_id} does not exist."
            if "UniqueViolation" in str(error.args):
                error_message = f"Assignment rules for group with UUID {group_id} already exist."

        name = validated_create_assignment_rule.get("name")
        if name in str(error.args):
            error_message = f"An assignment rule with name {name} already exists."
        log_post_assignment_rule_failed(logger)
        return json_error_response("Integrity error", str(error_message), status.HTTP_400_BAD_REQUEST)

    log_post_assignment_rule_succeeded(logger, created_assignment_rule.get("id"))
    return flask_json_response(created_assignment_rule, status.HTTP_201_CREATED)

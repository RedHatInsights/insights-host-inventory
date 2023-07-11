from flask import current_app
from flask_api import status
from marshmallow import ValidationError
from sqlalchemy.exc import IntegrityError

from api import _error_json_response
from api import api_operation
from api import flask_json_response
from app.logging import get_logger
from app.models import InputAssignmentRule
from app.serialization import serialize_assignment_rule
from lib.assignment_rule_repository import add_assignment_rule


logger = get_logger(__name__)


@api_operation
def create_assignment_rule(body, rbac_filter=None):
    try:
        validated_create_assignment_rule = InputAssignmentRule().load(body)
    except ValidationError as e:
        logger.exception(f"Input validation error while creating assignment rule: {body}")
        return _error_json_response("Validation Error", str(e.messages))

    try:
        created_assignment_rule = add_assignment_rule(validated_create_assignment_rule)
        created_assignment_rule = serialize_assignment_rule(created_assignment_rule)
    except IntegrityError as error:
        return _error_json_response("Integrity Error", str(error))

    return flask_json_response(created_assignment_rule, status.HTTP_201_CREATED)

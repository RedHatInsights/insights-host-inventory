from flask_api import status
from marshmallow import ValidationError
from sqlalchemy.exc import IntegrityError

from api import api_operation
from api import flask_json_response
from api import json_error_response
from api import metrics
from app import RbacPermission
from app import RbacResourceType
from app.instrumentation import log_create_account_staleness_failed
from app.instrumentation import log_create_account_staleness_succeeded
from app.logging import get_logger
from app.models import InputAccountStalenessSchema
from app.serialization import serialize_account_staleness
from lib.account_staleness import add_account_staleness
from lib.middleware import rbac

logger = get_logger(__name__)


def _get_return_data():
    # This is mock result, will be changed during each endpoint task work
    return {
        "id": "1ba078bb-8461-474c-8498-1e50a1975cfb",
        "account_id": "0123456789",
        "org_id": "123",
        "conventional_staleness_delta": "1",
        "conventional_stale_warning_delta": "7",
        "conventional_culling_delta": "14",
        "immutable_staleness_delta": "2",
        "immutable_stale_warning_delta": "120",
        "immutable_culling_delta": "180",
        "created_at": "2023-07-28T14:32:16.353082",
        "updated_at": "2023-07-28T14:32:16.353082",
    }


@api_operation
@rbac(RbacResourceType.STALENESS, RbacPermission.READ)
@metrics.api_request_time.time()
def get_staleness():
    return flask_json_response(_get_return_data(), status.HTTP_200_OK)


@api_operation
@rbac(RbacResourceType.STALENESS, RbacPermission.WRITE)
@metrics.api_request_time.time()
def create_staleness(body):
    # Validate account staleness input data
    try:
        validated_data = InputAccountStalenessSchema().load(body)
    except ValidationError as e:
        logger.exception(f'Input validation error, "{str(e.messages)}", while creating account staleness: {body}')
        return json_error_response("Validation Error", str(e.messages), status.HTTP_400_BAD_REQUEST)

    try:
        # Create account staleness with validated data
        created_staleness = add_account_staleness(validated_data)

        log_create_account_staleness_succeeded(logger, created_staleness.id)
    except IntegrityError:
        error_message = f'An account staleness with org_id {validated_data.get("org_id")} already exists.'

        log_create_account_staleness_failed(logger, validated_data.get("org_id"))
        logger.exception(error_message)
        return json_error_response("Integrity error", error_message, status.HTTP_400_BAD_REQUEST)

    return flask_json_response(serialize_account_staleness(created_staleness), status.HTTP_201_CREATED)


@api_operation
@rbac(RbacResourceType.STALENESS, RbacPermission.WRITE)
@metrics.api_request_time.time()
def update_staleness():
    return flask_json_response(_get_return_data(), status.HTTP_200_OK)


@api_operation
@rbac(RbacResourceType.STALENESS, RbacPermission.WRITE)
@metrics.api_request_time.time()
def reset_staleness():
    return flask_json_response(_get_return_data(), status.HTTP_200_OK)

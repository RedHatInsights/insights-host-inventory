from flask import abort
from flask import Response
from flask_api import status
from marshmallow import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import NoResultFound

from api import api_operation
from api import flask_json_response
from api import json_error_response
from api import metrics
from app import RbacPermission
from app import RbacResourceType
from app.auth import get_current_identity
from app.instrumentation import log_create_account_staleness_failed
from app.instrumentation import log_create_account_staleness_succeeded
from app.instrumentation import log_patch_account_staleness_succeeded
from app.logging import get_logger
from app.models import InputAccountStalenessSchema
from app.serialization import serialize_account_staleness_response
from lib.account_staleness import add_account_staleness
from lib.account_staleness import patch_account_staleness
from lib.account_staleness import remove_account_staleness
from lib.feature_flags import FLAG_INVENTORY_CUSTOM_STALENESS
from lib.feature_flags import get_flag_value
from lib.middleware import rbac
from lib.middleware import RbacFilter

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


def _validate_input_data(body):
    # Validate account staleness input data
    try:
        validated_data = InputAccountStalenessSchema().load(body)
    except ValidationError as e:
        logger.exception(f'Input validation error, "{str(e.messages)}", while creating account staleness: {body}')
        return json_error_response("Validation Error", str(e.messages), status.HTTP_400_BAD_REQUEST)

    return validated_data


@api_operation
@rbac(RbacResourceType.STALENESS, RbacPermission.READ)
@metrics.api_request_time.time()
def get_staleness(rbac_filter: RbacFilter):
    return flask_json_response(_get_return_data(), status.HTTP_200_OK)


@api_operation
@rbac(RbacResourceType.STALENESS, RbacPermission.WRITE)
@metrics.api_request_time.time()
def create_staleness(body, rbac_filter: RbacFilter):
    if not get_flag_value(FLAG_INVENTORY_CUSTOM_STALENESS):
        return Response(None, status.HTTP_501_NOT_IMPLEMENTED)

    current_identity = get_current_identity()
    org_id = current_identity.org_id

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
        error_message = f"An account staleness with org_id {org_id} already exists."

        log_create_account_staleness_failed(logger, org_id)
        logger.exception(error_message)
        return json_error_response("Integrity error", error_message, status.HTTP_400_BAD_REQUEST)

    return flask_json_response(serialize_account_staleness_response(created_staleness), status.HTTP_201_CREATED)


@api_operation
@rbac(RbacResourceType.STALENESS, RbacPermission.WRITE)
@metrics.api_request_time.time()
def delete_staleness(rbac_filter: RbacFilter):
    if not get_flag_value(FLAG_INVENTORY_CUSTOM_STALENESS):
        return Response(None, status.HTTP_501_NOT_IMPLEMENTED)

    try:
        remove_account_staleness()
        return flask_json_response(None, status.HTTP_204_NO_CONTENT)
    except NoResultFound:
        abort(status.HTTP_404_NOT_FOUND, "Account Staleness not found.")


@api_operation
@rbac(RbacResourceType.STALENESS, RbacPermission.WRITE)
@metrics.api_request_time.time()
def update_staleness(body, rbac_filter: RbacFilter):
    if not get_flag_value(FLAG_INVENTORY_CUSTOM_STALENESS):
        return Response(None, status.HTTP_501_NOT_IMPLEMENTED)

    validated_data = _validate_input_data(body)

    try:
        updated_staleness = patch_account_staleness(validated_data)
        if updated_staleness is None:
            # since update only return None with no record instead of exception.
            raise NoResultFound

        log_patch_account_staleness_succeeded(logger, updated_staleness.id)

        return flask_json_response(serialize_account_staleness_response(updated_staleness), status.HTTP_200_OK)
    except NoResultFound:
        abort(status.HTTP_404_NOT_FOUND, "Account Staleness not found.")


@api_operation
@rbac(RbacResourceType.STALENESS, RbacPermission.WRITE)
@metrics.api_request_time.time()
def reset_staleness(rbac_filter: RbacFilter):
    return flask_json_response(_get_return_data(), status.HTTP_200_OK)

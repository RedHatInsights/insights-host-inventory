from http import HTTPStatus

from flask import abort
from flask import Response
from marshmallow import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import NoResultFound

from api import api_operation
from api import flask_json_response
from api import json_error_response
from api import metrics
from api.cache import delete_cached_system_keys
from api.staleness_query import get_staleness_obj
from api.staleness_query import get_sys_default_staleness_api
from app import RbacPermission
from app import RbacResourceType
from app.auth import get_current_identity
from app.instrumentation import log_create_staleness_failed
from app.instrumentation import log_create_staleness_succeeded
from app.instrumentation import log_patch_staleness_succeeded
from app.logging import get_logger
from app.models import StalenessSchema
from app.serialization import serialize_staleness_response
from app.serialization import serialize_staleness_to_dict
from lib.feature_flags import FLAG_INVENTORY_CUSTOM_STALENESS
from lib.feature_flags import get_flag_value
from lib.middleware import rbac
from lib.staleness import add_staleness
from lib.staleness import patch_staleness
from lib.staleness import remove_staleness

logger = get_logger(__name__)


def _validate_input_data(body):
    # Validate account staleness input data
    try:
        identity = get_current_identity()
        staleness_obj = serialize_staleness_to_dict(get_staleness_obj(identity))
        validated_data = StalenessSchema().load({**staleness_obj, **body})

        return validated_data

    except ValidationError as e:
        logger.exception(f'Input validation error, "{str(e.messages)}", while creating account staleness: {body}')
        abort(HTTPStatus.BAD_REQUEST, f"Validation Error: {str(e.messages)}")


@api_operation
@rbac(RbacResourceType.STALENESS, RbacPermission.READ, permission_base="staleness")
@rbac(RbacResourceType.HOSTS, RbacPermission.READ)
@metrics.api_request_time.time()
def get_staleness(rbac_filter=None):
    try:
        staleness = get_staleness_obj()
        staleness = serialize_staleness_response(staleness)

        return flask_json_response(staleness, HTTPStatus.OK)
    except ValueError as e:
        abort(HTTPStatus.BAD_REQUEST, str(e))


@api_operation
@rbac(RbacResourceType.STALENESS, RbacPermission.READ, permission_base="staleness")
@rbac(RbacResourceType.HOSTS, RbacPermission.READ)
@metrics.api_request_time.time()
def get_default_staleness(rbac_filter=None):
    try:
        identity = get_current_identity()
        staleness = get_sys_default_staleness_api(identity)
        staleness = serialize_staleness_response(staleness)

        return flask_json_response(staleness, HTTPStatus.OK)
    except ValueError as e:
        abort(HTTPStatus.BAD_REQUEST, str(e))


@api_operation
@rbac(RbacResourceType.STALENESS, RbacPermission.WRITE, permission_base="staleness")
@rbac(RbacResourceType.HOSTS, RbacPermission.WRITE)
@metrics.api_request_time.time()
def create_staleness(body):
    if not get_flag_value(FLAG_INVENTORY_CUSTOM_STALENESS):
        return Response(None, HTTPStatus.NOT_IMPLEMENTED)

    # Validate account staleness input data
    org_id = get_current_identity().org_id
    try:
        validated_data = _validate_input_data(body)
    except ValidationError as e:
        logger.exception(f'Input validation error, "{str(e.messages)}", while creating account staleness: {body}')
        return json_error_response("Validation Error", str(e.messages), HTTPStatus.BAD_REQUEST)

    try:
        # Create account staleness with validated data
        created_staleness = add_staleness(validated_data)
        delete_cached_system_keys(org_id=org_id)
        log_create_staleness_succeeded(logger, created_staleness.id)
    except IntegrityError:
        error_message = f"Staleness record for org_id {org_id} already exists."

        log_create_staleness_failed(logger, org_id)
        logger.exception(error_message)
        return json_error_response("Integrity error", error_message, HTTPStatus.BAD_REQUEST)

    return flask_json_response(serialize_staleness_response(created_staleness), HTTPStatus.CREATED)


@api_operation
@rbac(RbacResourceType.STALENESS, RbacPermission.WRITE, permission_base="staleness")
@rbac(RbacResourceType.HOSTS, RbacPermission.WRITE)
@metrics.api_request_time.time()
def delete_staleness():
    if not get_flag_value(FLAG_INVENTORY_CUSTOM_STALENESS):
        return Response(None, HTTPStatus.NOT_IMPLEMENTED)

    org_id = get_current_identity().org_id
    try:
        remove_staleness()
        delete_cached_system_keys(org_id=org_id)
        return flask_json_response(None, HTTPStatus.NO_CONTENT)
    except NoResultFound:
        abort(
            HTTPStatus.NOT_FOUND,
            f"Staleness record for org_id {org_id} does not exist.",
        )


@api_operation
@rbac(RbacResourceType.STALENESS, RbacPermission.WRITE, permission_base="staleness")
@rbac(RbacResourceType.HOSTS, RbacPermission.WRITE)
@metrics.api_request_time.time()
def update_staleness(body):
    if not get_flag_value(FLAG_INVENTORY_CUSTOM_STALENESS):
        return Response(None, HTTPStatus.NOT_IMPLEMENTED)

    # Validate account staleness input data
    try:
        validated_data = _validate_input_data(body)
    except ValidationError as e:
        logger.exception(f'Input validation error, "{str(e.messages)}", while creating account staleness: {body}')
        return json_error_response("Validation Error", str(e.messages), HTTPStatus.BAD_REQUEST)

    org_id = get_current_identity().org_id
    try:
        updated_staleness = patch_staleness(validated_data)
        if updated_staleness is None:
            # since update only return None with no record instead of exception.
            raise NoResultFound

        delete_cached_system_keys(org_id=org_id)
        log_patch_staleness_succeeded(logger, updated_staleness.id)

        return flask_json_response(serialize_staleness_response(updated_staleness), HTTPStatus.OK)
    except NoResultFound:
        abort(
            HTTPStatus.NOT_FOUND,
            f"Staleness record for org_id {org_id} does not exist.",
        )

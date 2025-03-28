from http import HTTPStatus
from threading import Thread

from flask import abort
from flask import current_app
from marshmallow import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import NoResultFound

from api import api_operation
from api import flask_json_response
from api import json_error_response
from api import metrics
from api.cache import delete_cached_system_keys
from api.staleness_query import get_staleness_obj
from app import RbacPermission
from app import RbacResourceType
from app.auth import get_current_identity
from app.instrumentation import log_create_staleness_failed
from app.instrumentation import log_create_staleness_succeeded
from app.instrumentation import log_patch_staleness_succeeded
from app.logging import get_logger
from app.models import Host
from app.models import StalenessSchema
from app.serialization import serialize_staleness_response
from app.serialization import serialize_staleness_to_dict
from app.staleness_serialization import get_sys_default_staleness_api
from lib.feature_flags import FLAG_INVENTORY_CREATE_LAST_CHECK_IN_UPDATE_PER_REPORTER_STALENESS
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
        staleness_obj = serialize_staleness_to_dict(get_staleness_obj(identity.org_id))
        validated_data = StalenessSchema().load({**staleness_obj, **body})

        return validated_data

    except ValidationError as e:
        logger.exception(f'Input validation error, "{str(e.messages)}", while creating account staleness: {body}')
        abort(HTTPStatus.BAD_REQUEST, f"Validation Error: {str(e.messages)}")


def _update_hosts_staleness_async(org_id, app):
    with app.app_context():
        logger.debug("Starting host staleness update thread")
        try:
            logger.info(f"Querying hosts for org_id: {org_id}")
            hosts_query = Host.query.filter(Host.org_id == org_id)
            num_hosts = hosts_query.count()
            if num_hosts > 0:
                logger.info(f"Found {num_hosts} hosts for org_id: {org_id}")
                for host in hosts_query.yield_per(500):
                    host._update_all_per_reporter_staleness()
                hosts_query.session.commit()

                delete_cached_system_keys(org_id=org_id, spawn=True)
            logger.info("Leaving host staleness update thread")
        except Exception as e:
            raise e


def _validate_flag_and_call_thread(org_id):
    """
    This method validates if feature flag is enabled,
    is it is, call the async host staleness update,
    otherwise, just delete the cache as usual
    """
    if get_flag_value(FLAG_INVENTORY_CREATE_LAST_CHECK_IN_UPDATE_PER_REPORTER_STALENESS):
        update_hosts_thread = Thread(
            target=_update_hosts_staleness_async,
            daemon=True,
            args=(
                org_id,
                current_app._get_current_object(),
            ),
        )
        update_hosts_thread.start()
    else:
        delete_cached_system_keys(org_id=org_id, spawn=True)


@api_operation
@rbac(RbacResourceType.STALENESS, RbacPermission.READ, permission_base="staleness")
@rbac(RbacResourceType.HOSTS, RbacPermission.READ)
@metrics.api_request_time.time()
def get_staleness(rbac_filter=None):  # noqa: ARG001, 'rbac_filter' is required for all API endpoints
    try:
        staleness = get_staleness_obj(get_current_identity().org_id)
        staleness = serialize_staleness_response(staleness)

        return flask_json_response(staleness, HTTPStatus.OK)
    except ValueError as e:
        abort(HTTPStatus.BAD_REQUEST, str(e))


@api_operation
@rbac(RbacResourceType.STALENESS, RbacPermission.READ, permission_base="staleness")
@rbac(RbacResourceType.HOSTS, RbacPermission.READ)
@metrics.api_request_time.time()
def get_default_staleness(rbac_filter=None):  # noqa: ARG001, 'rbac_filter' is required for all API endpoints
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
        _validate_flag_and_call_thread(org_id)
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
    org_id = get_current_identity().org_id
    try:
        remove_staleness()
        _validate_flag_and_call_thread(org_id)
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

        _validate_flag_and_call_thread(org_id)

        log_patch_staleness_succeeded(logger, updated_staleness.id)

        return flask_json_response(serialize_staleness_response(updated_staleness), HTTPStatus.OK)
    except NoResultFound:
        abort(
            HTTPStatus.NOT_FOUND,
            f"Staleness record for org_id {org_id} does not exist.",
        )

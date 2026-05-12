from __future__ import annotations

from http import HTTPStatus

import sqlalchemy as sa
from flask import Response
from flask import abort
from marshmallow import ValidationError
from sqlalchemy import orm
from sqlalchemy.engine.base import Connection
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapper
from sqlalchemy.orm.exc import NoResultFound

from api import api_operation
from api import flask_json_response
from api import json_error_response
from api import metrics
from api.staleness_query import get_staleness_obj
from app.auth import get_current_identity
from app.auth.identity import Identity
from app.auth.rbac import KesselResourceTypes
from app.instrumentation import log_create_staleness_failed
from app.instrumentation import log_create_staleness_succeeded
from app.instrumentation import log_patch_staleness_succeeded
from app.logging import get_logger
from app.models import Host
from app.models import Staleness
from app.models import StalenessSchema
from app.models.utils import StalenessCache
from app.serialization import serialize_staleness_response
from app.serialization import serialize_staleness_to_dict
from app.staleness_serialization import get_sys_default_staleness_api
from lib.middleware import access
from lib.staleness import add_staleness
from lib.staleness import patch_staleness
from lib.staleness import remove_staleness
from lib.staleness import remove_staleness_if_exists
from lib.staleness import staleness_equivalent_to_system_defaults

logger = get_logger(__name__)


def _response_if_staleness_equivalent_to_system_defaults(
    validated_data: dict,
    identity: Identity,
    org_id: str,
    success_status: HTTPStatus,
) -> Response | None:
    """If validated data is strictly under 1h from system defaults, drop custom row and return JSON."""
    sys_defaults = get_sys_default_staleness_api(identity)
    if not staleness_equivalent_to_system_defaults(validated_data, identity, sys_defaults=sys_defaults):
        return None
    if remove_staleness_if_exists():
        StalenessCache.delete(org_id)
    return flask_json_response(serialize_staleness_response(sys_defaults), success_status)


def _validate_input_data(body):
    # Validate account staleness input data
    try:
        # TODO(gchamoul): Remove this filtering when the immutable fields are
        # fully deprecated and removed from the API spec.
        # Filter out immutable staleness fields that are no longer supported
        immutable_fields = {
            "immutable_time_to_delete",
            "immutable_time_to_stale",
            "immutable_time_to_stale_warning",
        }
        filtered_body = {k: v for k, v in body.items() if k not in immutable_fields}

        identity = get_current_identity()
        staleness_obj = serialize_staleness_to_dict(get_staleness_obj(identity.org_id))
        validated_data = StalenessSchema().load({**staleness_obj, **filtered_body})

        return validated_data

    except ValidationError as e:
        logger.exception(f'Input validation error, "{str(e.messages)}", while creating account staleness: {body}')
        abort(HTTPStatus.BAD_REQUEST, f"Validation Error: {str(e.messages)}")


@sa.event.listens_for(Host, "before_update")
def receive_before_host_update(mapper: Mapper, connection: Connection, host: Host):  # noqa: ARG001
    """Prevent host modified_on update during staleness updates.

    This SQLAlchemy event listener, triggered before any host update,
    prevents the ``modified_on`` timestamp from being updated when only
    the ``per_reporter_staleness`` field is changed.  This avoids
    unnecessary updates as ``modified_on`` is automatically updated for
    every change to a Host object, which can lead to confusion to the user.

    For more details on SQLAlchemy event listeners, see:
    https://docs.sqlalchemy.org/en/20/orm/events.html#sqlalchemy.orm.MapperEvents.before_update

    :param mapper: The SQLAlchemy mapper.
    :param connection: The database connection.
    :param host: The Host object being updated.
    """
    host_details = sa.inspect(host)
    prs_changed, _, _ = host_details.attrs.per_reporter_staleness.history
    staleness_changed, _, _ = host_details.attrs.deletion_timestamp.history
    if prs_changed or staleness_changed:
        orm.attributes.flag_modified(host, "modified_on")


@api_operation
@access(KesselResourceTypes.STALENESS.view)
@access(KesselResourceTypes.HOST.view)
@metrics.api_request_time.time()
def get_staleness(rbac_filter=None):  # noqa: ARG001, 'rbac_filter' is required for all API endpoints
    try:
        staleness = get_staleness_obj(get_current_identity().org_id)
        staleness = serialize_staleness_response(staleness)

        return flask_json_response(staleness, HTTPStatus.OK)
    except ValueError as e:
        abort(HTTPStatus.BAD_REQUEST, str(e))


@api_operation
@access(KesselResourceTypes.STALENESS.view)
@access(KesselResourceTypes.HOST.view)
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
@access(KesselResourceTypes.STALENESS.update)
@access(KesselResourceTypes.HOST.update)
@metrics.api_request_time.time()
def create_staleness(body):
    # Validate account staleness input data
    identity = get_current_identity()
    org_id = identity.org_id
    validated_data = _validate_input_data(body)

    early = _response_if_staleness_equivalent_to_system_defaults(validated_data, identity, org_id, HTTPStatus.CREATED)
    if early is not None:
        return early

    try:
        # Create account staleness with validated data
        created_staleness = add_staleness(validated_data)
        StalenessCache.delete(org_id)
        log_create_staleness_succeeded(logger, created_staleness.id)
    except IntegrityError:
        error_message = f"Staleness record for org_id {org_id} already exists."

        log_create_staleness_failed(logger, org_id)
        logger.exception(error_message)
        return json_error_response("Integrity error", error_message, HTTPStatus.BAD_REQUEST)

    return flask_json_response(serialize_staleness_response(created_staleness), HTTPStatus.CREATED)


@api_operation
@access(KesselResourceTypes.STALENESS.update)
@access(KesselResourceTypes.HOST.update)
@metrics.api_request_time.time()
def delete_staleness():
    identity = get_current_identity()
    org_id = identity.org_id
    try:
        remove_staleness()
        StalenessCache.delete(org_id)
        return flask_json_response(None, HTTPStatus.NO_CONTENT)
    except NoResultFound:
        abort(
            HTTPStatus.NOT_FOUND,
            f"Staleness record for org_id {org_id} does not exist.",
        )


@api_operation
@access(KesselResourceTypes.STALENESS.update)
@access(KesselResourceTypes.HOST.update)
@metrics.api_request_time.time()
def update_staleness(body):
    # Validate account staleness input data
    validated_data = _validate_input_data(body)
    identity = get_current_identity()
    org_id = identity.org_id

    # PATCH must only update an existing custom row. If there is no row, return 404
    # (pre-RHINENG-20674 behavior), even when the payload is default-equivalent.
    early = None
    if Staleness.query.filter(Staleness.org_id == org_id).first() is not None:
        early = _response_if_staleness_equivalent_to_system_defaults(validated_data, identity, org_id, HTTPStatus.OK)
    if early is not None:
        return early

    try:
        updated_staleness = patch_staleness(validated_data)
        StalenessCache.delete(org_id)
        if updated_staleness is None:
            # since update only return None with no record instead of exception.
            raise NoResultFound

        log_patch_staleness_succeeded(logger, updated_staleness.id)

        return flask_json_response(serialize_staleness_response(updated_staleness), HTTPStatus.OK)
    except NoResultFound:
        abort(
            HTTPStatus.NOT_FOUND,
            f"Staleness record for org_id {org_id} does not exist.",
        )

from http import HTTPStatus

from flask import Response
from flask import abort
from marshmallow import ValidationError

from api import api_operation
from api import build_collection_response
from api import flask_json_response
from api import json_error_response
from api import metrics
from api.views_validation import validate_view_configuration
from app.auth import get_current_identity
from app.auth.identity import IdentityType
from app.exceptions import ValidationException
from app.models.schemas.views import InputViewSchema
from app.models.schemas.views import PatchViewSchema
from app.serialization import serialize_view
from lib.views_repository import ViewNotFoundError
from lib.views_repository import ViewPermissionError
from lib.views_repository import create_view as repo_create_view
from lib.views_repository import delete_view as repo_delete_view
from lib.views_repository import get_view_by_id as repo_get_view_by_id
from lib.views_repository import get_views_list as repo_get_views_list
from lib.views_repository import update_view as repo_update_view


def _get_view_identity():
    identity = get_current_identity()

    if identity.identity_type not in (IdentityType.USER, IdentityType.SERVICE_ACCOUNT):
        abort(HTTPStatus.FORBIDDEN, "Identity type not supported. Use User or ServiceAccount identity.")

    if identity.identity_type == IdentityType.USER:
        user_id = getattr(identity, "user", {}).get("user_id")
    else:
        user_id = getattr(identity, "service_account", {}).get("user_id")

    if not user_id:
        abort(HTTPStatus.FORBIDDEN, "user_id is required.")

    return identity.org_id, user_id


@api_operation
@metrics.api_request_time.time()
def get_views_list(page=1, per_page=50, **kwargs):  # noqa: ARG001
    org_id, user_id = _get_view_identity()

    views, total = repo_get_views_list(org_id, user_id, page, per_page)

    serialized = [serialize_view(v, user_id) for v in views]
    return flask_json_response(build_collection_response(serialized, page, per_page, total))


@api_operation
@metrics.api_request_time.time()
def get_view_by_id(view_id, **kwargs):  # noqa: ARG001
    org_id, user_id = _get_view_identity()

    try:
        view = repo_get_view_by_id(view_id, org_id, user_id)
    except ViewNotFoundError:
        abort(HTTPStatus.NOT_FOUND, "View not found.")

    return flask_json_response(serialize_view(view, user_id))


@api_operation
@metrics.api_request_time.time()
def create_view(body, **kwargs):  # noqa: ARG001
    org_id, user_id = _get_view_identity()

    try:
        validated_data = InputViewSchema().load(body)
    except ValidationError as e:
        return json_error_response("Validation Error", str(e.messages), HTTPStatus.BAD_REQUEST)

    try:
        validate_view_configuration(validated_data["configuration"])
    except ValidationException as e:
        return json_error_response("Validation Error", str(e.detail), HTTPStatus.BAD_REQUEST)

    view = repo_create_view(validated_data, org_id, user_id)
    return flask_json_response(serialize_view(view, user_id), HTTPStatus.CREATED)


@api_operation
@metrics.api_request_time.time()
def update_view(view_id, body, **kwargs):  # noqa: ARG001
    org_id, user_id = _get_view_identity()

    try:
        validated_data = PatchViewSchema().load(body)
    except ValidationError as e:
        return json_error_response("Validation Error", str(e.messages), HTTPStatus.BAD_REQUEST)

    if not validated_data:
        return json_error_response(
            "Validation Error", "Request body must contain at least one field to update.", HTTPStatus.BAD_REQUEST
        )

    if "configuration" in validated_data:
        try:
            validate_view_configuration(validated_data["configuration"])
        except ValidationException as e:
            return json_error_response("Validation Error", str(e.detail), HTTPStatus.BAD_REQUEST)

    try:
        view = repo_update_view(view_id, validated_data, org_id, user_id)
    except ViewNotFoundError:
        abort(HTTPStatus.NOT_FOUND, "View not found.")
    except ViewPermissionError as e:
        abort(HTTPStatus.FORBIDDEN, str(e.detail))

    return flask_json_response(serialize_view(view, user_id))


@api_operation
@metrics.api_request_time.time()
def delete_view(view_id, **kwargs):  # noqa: ARG001
    org_id, user_id = _get_view_identity()

    try:
        repo_delete_view(view_id, org_id, user_id)
    except ViewNotFoundError:
        abort(HTTPStatus.NOT_FOUND, "View not found.")
    except ViewPermissionError as e:
        abort(HTTPStatus.FORBIDDEN, str(e.detail))

    return Response(None, HTTPStatus.NO_CONTENT)


def clone_view(view_id, **kwargs):  # noqa: ARG001
    abort(HTTPStatus.NOT_IMPLEMENTED)

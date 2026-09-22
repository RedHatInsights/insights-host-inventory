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
from app.models.schemas.views import DefaultViewSchema
from app.models.schemas.views import InputViewSchema
from app.models.schemas.views import PatchViewSchema
from app.serialization import serialize_view
from lib.views_repository import clone_view as repo_clone_view
from lib.views_repository import create_view as repo_create_view
from lib.views_repository import delete_default_view as repo_delete_default_view
from lib.views_repository import delete_view as repo_delete_view
from lib.views_repository import get_default_view_id as repo_get_default_view_id
from lib.views_repository import get_view_by_id as repo_get_view_by_id
from lib.views_repository import get_views_list as repo_get_views_list
from lib.views_repository import set_default_view as repo_set_default_view
from lib.views_repository import update_view as repo_update_view


def _get_view_identity():
    identity = get_current_identity()

    if identity.identity_type not in (IdentityType.USER, IdentityType.SERVICE_ACCOUNT):
        abort(HTTPStatus.FORBIDDEN, "Identity type not supported. Use User or ServiceAccount identity.")

    if not identity.user_id:
        abort(HTTPStatus.FORBIDDEN, "user_id is required.")

    return identity.org_id, identity.user_id


@api_operation
@metrics.api_request_time.time()
def get_views_list(page=1, per_page=50, **kwargs):  # noqa: ARG001
    org_id, user_id = _get_view_identity()

    views, total = repo_get_views_list(org_id, user_id, page, per_page)
    default_view_id = repo_get_default_view_id(org_id, user_id)

    serialized = [serialize_view(v, user_id) for v in views]
    response = build_collection_response(serialized, page, per_page, total)
    response["default_view_id"] = default_view_id
    return flask_json_response(response)


@api_operation
@metrics.api_request_time.time()
def get_view_by_id(view_id, **kwargs):  # noqa: ARG001
    org_id, user_id = _get_view_identity()

    view = repo_get_view_by_id(view_id, org_id, user_id)
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
def patch_view(view_id, body, **kwargs):  # noqa: ARG001
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

    view = repo_update_view(view_id, validated_data, org_id, user_id)
    return flask_json_response(serialize_view(view, user_id))


@api_operation
@metrics.api_request_time.time()
def delete_view(view_id, **kwargs):  # noqa: ARG001
    org_id, user_id = _get_view_identity()

    repo_delete_view(view_id, org_id, user_id)
    return Response(None, HTTPStatus.NO_CONTENT)


@api_operation
@metrics.api_request_time.time()
def clone_view(view_id, **kwargs):  # noqa: ARG001
    org_id, user_id = _get_view_identity()

    cloned = repo_clone_view(view_id, org_id, user_id)
    return flask_json_response(serialize_view(cloned, user_id), HTTPStatus.CREATED)


@api_operation
@metrics.api_request_time.time()
def set_default_view(body, **kwargs):  # noqa: ARG001
    org_id, user_id = _get_view_identity()

    try:
        validated_data = DefaultViewSchema().load(body)
    except ValidationError as e:
        return json_error_response("Validation Error", str(e.messages), HTTPStatus.BAD_REQUEST)

    view = repo_set_default_view(org_id, user_id, str(validated_data["view_id"]))
    return flask_json_response(serialize_view(view, user_id))


@api_operation
@metrics.api_request_time.time()
def delete_default_view(**kwargs):  # noqa: ARG001
    org_id, user_id = _get_view_identity()

    repo_delete_default_view(org_id, user_id)

    return Response(None, HTTPStatus.NO_CONTENT)

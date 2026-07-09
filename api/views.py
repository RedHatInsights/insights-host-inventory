from http import HTTPStatus

from flask import abort
from marshmallow import ValidationError

from api import api_operation
from api import build_collection_response
from api import flask_json_response
from api import json_error_response
from api import metrics
from app.auth import get_current_identity
from app.auth.identity import IdentityType
from app.models.schemas.views import InputViewSchema
from app.serialization import serialize_view
from lib.views_repository import ViewNotFoundError
from lib.views_repository import create_view as repo_create_view
from lib.views_repository import get_view_by_id as repo_get_view_by_id
from lib.views_repository import get_views_list as repo_get_views_list


def _get_view_identity():
    identity = get_current_identity()

    if identity.identity_type not in (IdentityType.USER, IdentityType.SERVICE_ACCOUNT):
        abort(HTTPStatus.FORBIDDEN, "Identity type not supported. Use User or ServiceAccount identity.")

    if identity.identity_type == IdentityType.USER:
        username = getattr(identity, "user", {}).get("username")
    else:
        username = getattr(identity, "service_account", {}).get("username")

    if not username:
        abort(HTTPStatus.FORBIDDEN, "Username is required.")

    return identity.org_id, username


@api_operation
@metrics.api_request_time.time()
def get_views_list(page=1, per_page=50, **kwargs):  # noqa: ARG001
    org_id, username = _get_view_identity()

    views, total = repo_get_views_list(org_id, username, page, per_page)

    serialized = [serialize_view(v, username) for v in views]
    return flask_json_response(build_collection_response(serialized, page, per_page, total))


@api_operation
@metrics.api_request_time.time()
def get_view_by_id(view_id, **kwargs):  # noqa: ARG001
    org_id, username = _get_view_identity()

    try:
        view = repo_get_view_by_id(view_id, org_id, username)
    except ViewNotFoundError:
        abort(HTTPStatus.NOT_FOUND, "View not found.")

    return flask_json_response(serialize_view(view, username))


@api_operation
@metrics.api_request_time.time()
def create_view(body, **kwargs):  # noqa: ARG001
    org_id, username = _get_view_identity()

    try:
        validated_data = InputViewSchema().load(body)
    except ValidationError as e:
        return json_error_response("Validation Error", str(e.messages), HTTPStatus.BAD_REQUEST)

    view = repo_create_view(validated_data, org_id, username)
    return flask_json_response(serialize_view(view, username), HTTPStatus.CREATED)


def update_view(view_id, body, **kwargs):  # noqa: ARG001
    abort(HTTPStatus.NOT_IMPLEMENTED)


def delete_view(view_id, **kwargs):  # noqa: ARG001
    abort(HTTPStatus.NOT_IMPLEMENTED)


def clone_view(view_id, **kwargs):  # noqa: ARG001
    abort(HTTPStatus.NOT_IMPLEMENTED)

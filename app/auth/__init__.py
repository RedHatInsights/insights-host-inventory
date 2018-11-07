from app.auth.identity import from_encoded, validate
from flask import abort, request, _request_ctx_stack
from werkzeug.local import LocalProxy
from werkzeug.exceptions import Forbidden

__all__ = ["init_app", "current_identity"]

_IDENTITY_HEADER = "x-rh-identity"


def _validate_identity(payload):
    """
    Identity payload validation dummy. Fails if the data is empty.
    """
    if not payload:
        raise ValueError


def _before_request():
    try:
        payload = request.headers[_IDENTITY_HEADER]
    except KeyError:
        abort(Forbidden.code)

    try:
        identity = from_encoded(payload)
    except (TypeError, ValueError):
        abort(Forbidden.code)

    try:
        validate(identity)
    except ValueError:
        abort(Forbidden.code)

    ctx = _request_ctx_stack.top
    ctx.identity = identity


def init_app(flask_app):
    flask_app.before_request(_before_request)


def _get_identity():
    ctx = _request_ctx_stack.top
    return ctx.identity


current_identity = LocalProxy(_get_identity)

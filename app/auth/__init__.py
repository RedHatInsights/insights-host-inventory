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
        _validate_identity(payload)
    except (TypeError, ValueError):
        abort(Forbidden.code)

    ctx = _request_ctx_stack.top
    ctx.identity = payload


def init_app(flask_app):
    flask_app.before_request(_before_request)


def _get_identity():
    ctx = _request_ctx_stack.top
    return ctx.identity


current_identity = LocalProxy(_get_identity)

from app.auth.identity import from_encoded, validate
from flask import abort, current_app, request, _request_ctx_stack
from werkzeug.local import LocalProxy
from werkzeug.exceptions import Forbidden

__all__ = ["init_app", "current_identity", "NoIdentityError", "requires_identity"]

_IDENTITY_HEADER = "x-rh-identity"


class NoIdentityError(RuntimeError):
    pass


def _validate_identity(payload):
    """
    Identity payload validation dummy. Fails if the data is empty.
    """
    if not payload:
        raise ValueError


def _before_request():
    if not _current_view_requires_identity():
        return  # This function does not require authentication.

    try:
        payload = request.headers[_IDENTITY_HEADER]
    except KeyError:
        abort(Forbidden.code)

    try:
        identity = from_encoded(payload)
    except (KeyError, TypeError, ValueError):
        abort(Forbidden.code)

    try:
        validate(identity)
    except ValueError:
        abort(Forbidden.code)

    ctx = _request_ctx_stack.top
    ctx.identity = identity


def init_app(flask_app):
    flask_app.before_request(_before_request)


def requires_identity(view_func):
    view_func.requires_identity = True
    return view_func


def _get_identity():
    ctx = _request_ctx_stack.top
    try:
        return ctx.identity
    except AttributeError:
        raise NoIdentityError


def _current_view_requires_identity():
    return _view_requires_identity(_get_current_view_func())


def _view_requires_identity(view_func):
    return hasattr(view_func, "requires_identity") and view_func.requires_identity


def _get_current_view_func():
    endpoint = request.url_rule.endpoint
    return current_app.view_functions[endpoint]


current_identity = LocalProxy(_get_identity)

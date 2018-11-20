from app.auth.identity import from_encoded, validate
from flask import abort, current_app, request, _request_ctx_stack
from werkzeug.local import LocalProxy
from werkzeug.exceptions import Forbidden

__all__ = ["bypass_auth", "init_app", "current_identity"]

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
    view_func = _get_view_func()
    if hasattr(view_func, "bypass_auth") and view_func.bypass_auth:
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


def bypass_auth(view_func):
    """
    Decorates the given view function as not requiring the authentication HTTP header.
    """
    view_func.bypass_auth = True
    return view_func


def _get_identity():
    ctx = _request_ctx_stack.top

    try:
        return ctx.identity
    except AttributeError:
        raise NoIdentityError


def _get_view_func():
    endpoint = request.url_rule.endpoint
    return current_app.view_functions[endpoint]


current_identity = LocalProxy(_get_identity)

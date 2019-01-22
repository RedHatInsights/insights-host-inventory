import os
from functools import wraps
from app.auth.identity import from_encoded, validate, Identity
from flask import abort, current_app, request, _request_ctx_stack
from werkzeug.local import LocalProxy
from werkzeug.exceptions import Forbidden

__all__ = ["init_app", "current_identity", "NoIdentityError", "requires_identity"]

_IDENTITY_HEADER = "x-rh-identity"


class NoIdentityError(RuntimeError):
    """
    There is no current identity. The request is not authenticated.
    """
    pass


class InvalidIdentityError(ValueError):
    """
    The identity header is missing or invalid.
    """
    pass


def _pick_identity():
    if os.getenv("FLASK_DEBUG") and os.getenv("NOAUTH"):
        return Identity(account_number="0000001")
    else:
        try:
            payload = request.headers[_IDENTITY_HEADER]
        except KeyError as error:
            raise InvalidIdentityError(f"Identity header missing: KeyError {error}")

        try:
            return from_encoded(payload)
        except (KeyError, TypeError, ValueError) as error:
            error_type = type(error).__name__
            message = f"Identity header undecodable: {error_type} {error}"
            raise InvalidIdentityError(message)



def _validate(identity):
    try:
        validate(identity)
    except Exception as error:
        raise InvalidIdentityError(f"Identity header invalid: {error}")


def requires_identity(view_func):
    @wraps(view_func)
    def _wrapper(*args, **kwargs):
        try:
            identity = _pick_identity()
            _validate(identity)
        except InvalidIdentityError as exc:
            current_app.logger.warn(exc)
            abort(Forbidden.code)

        ctx = _request_ctx_stack.top
        ctx.identity = identity
        return view_func(*args, **kwargs)

    return _wrapper


def _get_identity():
    ctx = _request_ctx_stack.top
    try:
        return ctx.identity
    except AttributeError:
        raise NoIdentityError


current_identity = LocalProxy(_get_identity)

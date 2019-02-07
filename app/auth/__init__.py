import logging
import os

from functools import wraps
from app.auth.identity import from_encoded, validate, Identity
from flask import abort, request, _request_ctx_stack
from werkzeug.local import LocalProxy
from werkzeug.exceptions import Forbidden

__all__ = ["init_app", "current_identity", "NoIdentityError", "requires_identity"]

_IDENTITY_HEADER = "x-rh-identity"

logger = logging.getLogger(__name__)


class NoIdentityError(RuntimeError):
    pass


def _pick_identity():
    if os.getenv("FLASK_DEBUG") and os.getenv("NOAUTH"):
        return Identity(account_number="0000001")
    else:
        try:
            payload = request.headers[_IDENTITY_HEADER]
        except KeyError:
            logger.debug("Unable to retrieve identity header from request")
            abort(Forbidden.code)

        try:
            return from_encoded(payload)
        except (KeyError, TypeError, ValueError):
            logger.debug("Unable to decode identity header")
            abort(Forbidden.code)


def _validate(identity):
    try:
        validate(identity)
    except Exception:
        logger.debug("Failed to validate identity header value")
        abort(Forbidden.code)


def requires_identity(view_func):
    @wraps(view_func)
    def _wrapper(*args, **kwargs):
        identity = _pick_identity()
        _validate(identity)
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

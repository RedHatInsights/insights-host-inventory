import logging
import os

from functools import wraps
from app.auth.identity import validate, Identity, IdentityBuilder
from flask import abort, request, _request_ctx_stack
from werkzeug.local import LocalProxy
from werkzeug.exceptions import Forbidden

__all__ = ["current_identity", "NoIdentityError", "requires_identity"]

_IDENTITY_HEADER = "x-rh-identity"
_AUTHORIZATION_HEADER = "Authorization"


logger = logging.getLogger(__name__)


class NoIdentityError(RuntimeError):
    pass


def _pick_identity():
    identity = None

    if _disabled_authentication():
        identity = Identity(account_number="0000001")

    if identity is None:
        identity = _retrieve_identity_from_header()

    if identity is None:
        identity = _retrieve_identity_from_bearer()

    return identity


def _disabled_authentication():
    return os.getenv("FLASK_DEBUG") and os.getenv("NOAUTH")


def _retrieve_identity_from_header():
    try:
        identity_header = request.headers[_IDENTITY_HEADER]
    except KeyError:
        logger.debug("Unable to retrieve identity header from request")
        return None

    try:
        return IdentityBuilder.from_encoded_json(identity_header)
    except (KeyError, TypeError, ValueError):
        logger.debug("Unable to decode identity header")
        return None


def _retrieve_identity_from_bearer():
    try:
        auth_header = request.headers[_AUTHORIZATION_HEADER]
    except KeyError:
        logger.debug("Unable to retrieve %s header from request" % (_AUTHORIZATION_HEADER))
        return None

    bearer_token = auth_header.split()[1]

    try:
        return IdentityBuilder.from_bearer_token(bearer_token)
    except (KeyError, TypeError, ValueError):
        logger.debug("Unable to process %s header" % (_AUTHORIZATION_HEADER))
        return None


def _validate(identity):
    try:
        validate(identity)
    except Exception as e:
        logger.debug("Failed to validate identity header value: %s" % e)
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

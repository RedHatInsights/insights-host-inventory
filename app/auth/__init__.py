import connexion
from flask import request
from werkzeug.local import LocalProxy

from api.metrics import login_failure_count
from app import IDENTITY_HEADER
from app import REQUEST_ID_HEADER
from app import UNKNOWN_REQUEST_ID_VALUE
from app.auth.identity import from_auth_header
from app.auth.identity import from_bearer_token
from app.auth.identity import validate
from app.logging import get_logger

__all__ = ["current_identity", "bearer_token_handler", "authentication_header_handler"]

logger = get_logger(__name__)


def authentication_header_handler(apikey, required_scopes=None):
    try:
        identity = from_auth_header(apikey)
        validate(identity)
    except Exception:
        login_failure_count.inc()
        logger.debug("Failed to validate identity header value", exc_info=True)
        return None

    return {"uid": identity}


def bearer_token_handler(token):
    try:
        identity = from_bearer_token(token)
        validate(identity)
    except Exception:
        login_failure_count.inc()
        logger.debug("Failed to validate bearer token value", exc_info=True)
        return None

    return {"uid": identity}


def authenticated_request(method, *args, **kwargs):
    headers = kwargs.get("headers", {})
    headers[IDENTITY_HEADER] = request.headers[IDENTITY_HEADER]
    headers[REQUEST_ID_HEADER] = request.headers.get(REQUEST_ID_HEADER, UNKNOWN_REQUEST_ID_VALUE)
    authenticated_kwargs = {**kwargs, "headers": headers}
    return method(*args, **authenticated_kwargs)


def _get_identity():
    return connexion.context["user"]


current_identity = LocalProxy(_get_identity)

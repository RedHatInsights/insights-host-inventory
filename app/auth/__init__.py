import connexion

from api.metrics import login_failure_count
from app.auth.identity import from_bearer_token, from_auth_header, validate
from app.logging import get_logger
from werkzeug.local import LocalProxy

__all__ = ["current_identity",
           "bearer_token_handler",
           "authentication_header_handler"]

logger = get_logger(__name__)


def authentication_header_handler(apikey, required_scopes=None):
    try:
        identity = from_auth_header(apikey)
        validate(identity)
    except Exception:
        login_failure_count.inc()
        logger.debug("Failed to validate identity header value",
                     exc_info=True)
        return None

    return {"uid": identity}


def bearer_token_handler(token):
    try:
        identity = from_bearer_token(token)
        validate(identity)
    except Exception:
        login_failure_count.inc()
        logger.debug("Failed to validate bearer token value",
                     exc_info=True)
        return None

    return {"uid": identity}


def _get_identity():
    return connexion.context["user"]


current_identity = LocalProxy(_get_identity)

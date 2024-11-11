import connexion
from flask import abort

from api.metrics import login_failure_count
from app.auth.identity import from_auth_header
from app.auth.identity import from_bearer_token
from app.logging import get_logger

__all__ = ("authentication_header_handler", "bearer_token_handler")

logger = get_logger(__name__)


def authentication_header_handler(apikey, required_scopes=None):
    try:
        identity = from_auth_header(apikey)
    except Exception as exc:
        login_failure_count.inc()
        logger.error(str(exc), exc_info=True)
        raise connexion.exceptions.OAuthProblem("Invalid token") from exc

    return {"uid": identity}


def bearer_token_handler(token):
    try:
        identity = from_bearer_token(token)
    except Exception:
        login_failure_count.inc()
        logger.error("Failed to validate bearer token value", exc_info=True)
        abort(401, "Failed to validate bearer token value")

    return {"uid": identity}


def get_current_identity():
    return connexion.context.context["user"]

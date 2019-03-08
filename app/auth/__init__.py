import connexion
import logging

from app.auth.identity import validate, IdentityBuilder
from werkzeug.local import LocalProxy

__all__ = ["current_identity", "NoIdentityError",
           "bearer_token_handler", "authentication_header_handler"]

logger = logging.getLogger(__name__)


class NoIdentityError(RuntimeError):
    pass


def bearer_token_handler(token):
    try:
        identity = IdentityBuilder.from_bearer_token(token)
        validate(identity)
    except Exception as e:
        logger.debug("Failed to validate bearer token value",
                     exc_info=True)
        return None

    return {"uid": identity}


def authentication_header_handler(apikey, required_scopes=None):
    try:
        identity = IdentityBuilder.from_auth_header(apikey)
        validate(identity)
    except Exception as e:
        logger.debug("Failed to validate identity header value",
                     exc_info=True)
        return None

    return {"uid": identity}


def _get_identity():
    try:
        return connexion.context["user"]
    except AttributeError:
        raise NoIdentityError


current_identity = LocalProxy(_get_identity)

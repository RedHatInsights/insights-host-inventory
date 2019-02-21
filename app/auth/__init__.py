import connexion
import logging
import os

from app.auth.identity import validate, IdentityBuilder
from werkzeug.local import LocalProxy

__all__ = ["current_identity", "NoIdentityError",
           "token_validator", "header_validator"]

_IDENTITY_HEADER = "x-rh-identity"
_AUTHORIZATION_HEADER = "Authorization"


logger = logging.getLogger(__name__)


class NoIdentityError(RuntimeError):
    pass


def token_validator(token):
    print("token:", token)
    if _is_authentication_disabled():
        identity = IdentityBuilder.for_disabled_authentication()
    else:
        try:
            identity = IdentityBuilder.from_bearer_token(token)
            # FIXME:
            validate(identity)
        except Exception as e:
            logger.debug("Failed to validate bearer token value: %s" % e)
            return None

    #return {'sub': identity}
    return {'uid': identity}


def header_validator(apikey, required_scopes=None):
    print("apikey:", apikey)
    if _is_authentication_disabled():
        identity = IdentityBuilder.for_disabled_authentication()
    else:
        try:
            identity = IdentityBuilder.from_encoded_json(apikey)
            # FIXME:
            validate(identity)
        except Exception as e:
            logger.debug("Failed to validate identity header value: %s" % e)
            return None

    #return {'sub': identity}
    return {'uid': identity}


def _is_authentication_disabled():
    return os.getenv("FLASK_DEBUG") and os.getenv("NOAUTH")


def _get_identity():
    try:
        return connexion.context['user']
    except AttributeError:
        raise NoIdentityError


current_identity = LocalProxy(_get_identity)

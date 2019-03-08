import connexion
import logging

from app.auth.identity import from_encoded, validate
from werkzeug.local import LocalProxy

__all__ = ["current_identity"]

logger = logging.getLogger(__name__)


def authentication_header_handler(header_payload, required_scopes=None):
    try:
        identity = from_encoded(header_payload)
        validate(identity)
    except (KeyError, TypeError, ValueError):
        logger.debug("Unable to decode identity header",
                     exc_info=True)
        return None

    return {"uid": identity}


def _get_identity():
    return connexion.context["user"]


current_identity = LocalProxy(_get_identity)

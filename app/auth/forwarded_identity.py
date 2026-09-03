from __future__ import annotations

import uuid

from flask import has_request_context
from flask import request

from app.auth.identity import CertType
from app.auth.identity import Identity
from app.auth.identity import IdentityType
from app.exceptions import InventoryException
from app.validators import verify_uuid_format_draft4

FORWARDED_IDENTITY_HEADER = "X-Forwarded-Identity"


def get_satellite_forwarded_identity(identity: Identity) -> str | None:
    """
    Return the subscription_manager_id from X-Forwarded-Identity for satellite cert-auth requests.

    For satellite system identities, when the header is present and valid, returns the UUID string.
    When the header is absent, returns None (caller applies owner_id-only scoping).
    When the header is present but malformed, raises InventoryException with HTTP 403.
    For non-satellite identities, returns None and the header is ignored.
    """
    if identity.identity_type != IdentityType.SYSTEM:
        return None

    if identity.system.get("cert_type") != CertType.SATELLITE:
        return None

    if not has_request_context():
        return None

    header_value = request.headers.get(FORWARDED_IDENTITY_HEADER)
    if not header_value:
        return None

    header_value = header_value.strip()
    if not header_value:
        return None

    if not verify_uuid_format_draft4(header_value):
        raise InventoryException(
            status=403,
            title="Forbidden",
            detail="Invalid X-Forwarded-Identity header",
        )

    return str(uuid.UUID(header_value))

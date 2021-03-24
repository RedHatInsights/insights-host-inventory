import os
from base64 import b64decode
from enum import Enum
from json import loads

from app.logging import get_logger
from app.logging import threadctx


__all__ = ["Identity", "from_auth_header", "from_bearer_token", "validate"]

logger = get_logger(__name__)

SHARED_SECRET_ENV_VAR = "INVENTORY_SHARED_SECRET"


def from_auth_header(base64):
    json = b64decode(base64)
    identity_dict = loads(json)
    return Identity(identity_dict["identity"])


def from_bearer_token(token):
    return Identity(token=token)


class AuthType(str, Enum):
    BASIC = "basic-auth"
    CERT = "cert-auth"
    CLASSIC = "classic-proxy"


class CertType(str, Enum):
    SATELLITE = "satellite"
    SYSTEM = "system"


class IdentityType(str, Enum):
    SYSTEM = "System"
    USER = "User"
    CLASSIC = "Insights_Classic_System"


class Identity:
    def __init__(self, obj=None, token=None):
        """
        A "trusted" identity is trusted to be passing in
        the correct account number(s).
        """
        if not obj and not token:
            raise ValueError("Neither the account_number or token has been set")
        elif obj:
            self.is_trusted_system = False
            self.account_number = obj["account_number"]

            if obj.get("auth_type"):
                self.auth_type = obj["auth_type"]
            else:
                self.auth_type = None

            if obj["type"] == IdentityType.USER:
                self.identity_type = obj["type"]
                self.user = obj["user"]
            elif obj["type"] == IdentityType.SYSTEM:
                self.identity_type = obj["type"]
                self.system = obj["system"]

            # ensure account number availability
            if obj["account_number"] is None or obj["account_number"] == "":
                raise ValueError("Authentication type unknown")

            threadctx.account_number = obj["account_number"]
        else:
            self.token = token
            self.is_trusted_system = True
            threadctx.account_number = "<<TRUSTED IDENTITY>>"

    def _asdict(self):
        if self.identity_type == IdentityType.USER:
            return {
                "account_number": self.account_number,
                "type": self.identity_type,
                "auth_type": self.auth_type,
                "user": self.user.copy(),
            }
        if self.identity_type == IdentityType.SYSTEM:
            return {
                "account_number": self.account_number,
                "type": self.identity_type,
                "auth_type": self.auth_type,
                "system": self.system.copy(),
            }

    def __eq__(self, other):
        return self.account_number == other.account_number


def validate(identity):
    if identity.is_trusted_system:
        # This needs to be moved.
        # The logic for reading the environment variable and logging
        # a warning should go into the Config class
        shared_secret = os.getenv(SHARED_SECRET_ENV_VAR)
        if not shared_secret:
            logger.warning("%s environment variable is not set", SHARED_SECRET_ENV_VAR)
        if identity.token != shared_secret:
            raise ValueError("Invalid credentials")
    else:
        # Ensure the account number is present.
        if not identity.account_number:
            raise ValueError("The account_number is mandatory.")

        elif identity.identity_type == IdentityType.SYSTEM:
            if not identity.system:
                raise ValueError("The identity.system is mandatory")
            if not identity.system.get("cert_type"):
                raise ValueError("The cert_type field is mandatory.")
            if identity.system.get("cert_type") not in CertType.__members__.values():
                raise ValueError("The cert_type is invalid.")
            if not identity.system.get("cn"):
                raise ValueError("The cn field is mandatory.")
            if not identity.auth_type:
                raise ValueError("The auth_type field is mandatory.")
            if identity.auth_type not in AuthType.__members__.values():
                raise ValueError("The auth_type is invalid.")

        elif identity.identity_type == IdentityType.USER:
            if not identity.user:
                raise ValueError("The identity.user is mandatory")
            if not identity.user.get("email"):
                raise ValueError("For basic-auth email is mandatory")

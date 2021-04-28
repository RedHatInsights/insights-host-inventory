import os
from base64 import b64decode
from enum import Enum
from json import loads

from app.logging import get_logger
from app.logging import threadctx


__all__ = ["Identity", "from_auth_header", "from_bearer_token"]

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
    JWT = "jwt-auth"
    UHC = "uhc-auth"


class CertType(str, Enum):
    HYPERVISOR = "hypervisor"
    RHUI = "rhui"
    SAM = "sam"
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
        if token:
            # Treat as a trusted identity
            self.token = token
            self.is_trusted_system = True

            # This needs to be moved.
            # The logic for reading the environment variable and logging
            # a warning should go into the Config class
            shared_secret = os.getenv(SHARED_SECRET_ENV_VAR)
            if not shared_secret:
                logger.warning("%s environment variable is not set", SHARED_SECRET_ENV_VAR)
            if self.token != shared_secret:
                raise ValueError("Invalid credentials")

            threadctx.account_number = "<<TRUSTED IDENTITY>>"

        elif obj:
            # Ensure account number availability
            self.is_trusted_system = False
            self.account_number = obj.get("account_number")
            self.auth_type = obj.get("auth_type")
            self.identity_type = obj.get("type")

            if not self.account_number:
                raise ValueError("The account_number is mandatory.")
            elif not self.identity_type or self.identity_type not in IdentityType.__members__.values():
                raise ValueError("Identity type invalid or missing in provided Identity")
            elif self.auth_type and self.auth_type not in AuthType.__members__.values():
                raise ValueError(f"The auth_type {self.auth_type} is invalid")

            if obj["type"] == IdentityType.USER:
                self.user = obj.get("user")
                if not self.user:
                    raise ValueError("The identity.user field is mandatory for user-type identities")

            elif obj["type"] == IdentityType.SYSTEM:
                self.system = obj.get("system")
                if not self.system:
                    raise ValueError("The identity.system field is mandatory for system-type identities")
                elif not self.system.get("cert_type"):
                    raise ValueError("The cert_type field is mandatory for system-type identities")
                elif self.system.get("cert_type") not in CertType.__members__.values():
                    # TODO: Raise ValueError once we solidify all cert_type values
                    logger.error("The cert_type %s is invalid.", self.system.get("cert_type"))
                elif not self.system.get("cn"):
                    raise ValueError("The cn field is mandatory for system-type identities")

            threadctx.account_number = obj["account_number"]

        else:
            raise ValueError("Neither the account_number or token has been set")

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

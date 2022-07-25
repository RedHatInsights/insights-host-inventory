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
            threadctx.org_id = "<<TRUSTED IDENTITY>>"

        elif obj:
            self.is_trusted_system = False
            self.account_number = obj.get("account_number")
            self.auth_type = obj.get("auth_type")
            self.identity_type = obj.get("type")
            self.org_id = obj.get("org_id")

            # Ensure org_id availability
            if not self.org_id:
                raise ValueError("The org_id is mandatory.")
            elif not self.identity_type or self.identity_type not in IdentityType.__members__.values():
                raise ValueError("Identity type invalid or missing in provided Identity")
            elif self.auth_type is None:
                raise ValueError("Identity is missing auth_type field")
            elif self.auth_type is not None:
                self.auth_type = self.auth_type.lower()
                if self.auth_type not in AuthType.__members__.values():
                    raise ValueError(f"The auth_type {self.auth_type} is invalid")

            if self.identity_type == IdentityType.USER:
                self.user = obj.get("user")

            elif self.identity_type == IdentityType.SYSTEM:
                self.system = obj.get("system")
                if not self.system:
                    raise ValueError("The identity.system field is mandatory for system-type identities")
                elif not self.system.get("cert_type"):
                    raise ValueError("The cert_type field is mandatory for system-type identities")
                elif self.system["cert_type"].lower() not in CertType.__members__.values():
                    raise ValueError(f"The cert_type {self.system['cert_type']} is invalid.")
                elif not self.system.get("cn"):
                    raise ValueError("The cn field is mandatory for system-type identities")
                else:
                    self.system["cert_type"] = self.system["cert_type"].lower()

            threadctx.org_id = obj["org_id"]

            if obj.get("account_number"):
                threadctx.account_number = obj["account_number"]

        else:
            raise ValueError("Neither the org_id or token has been set")

    def _asdict(self):
        ident = {"type": self.identity_type, "auth_type": self.auth_type, "org_id": self.org_id}

        if hasattr(self, "account_number"):
            ident["account_number"] = self.account_number

        if self.identity_type == IdentityType.USER:
            ident["user"] = self.user.copy()
            return ident
        if self.identity_type == IdentityType.SYSTEM:
            ident["system"] = self.system.copy()
            return ident

    def __eq__(self, other):
        return self.org_id == other.org_id


# Messages from the system_profile topic don't need to provide a real Identity,
# So this helper function creates a basic User-type identity from the host data.
def create_mock_identity_with_org_id(org_id):
    return Identity({"org_id": org_id, "type": IdentityType.USER, "auth_type": AuthType.BASIC})

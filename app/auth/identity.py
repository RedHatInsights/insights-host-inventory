import os
from base64 import b64decode
from enum import Enum
from json import loads

import marshmallow as m

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
            result = IdentitySchema().load(obj)

            self.is_trusted_system = False
            self.account_number = result.get("account_number")
            self.auth_type = result.get("auth_type")
            self.identity_type = result.get("type")
            self.org_id = result.get("org_id")
            if "user" in result:
                self.user = result.get("user")
            if "system" in result:
                self.system = result.get("system")

            threadctx.org_id = self.org_id

            if self.account_number:
                threadctx.account_number = self.account_number

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


class IdentityLowerString(m.fields.String):
    def _deserialize(self, value, *args, **kwargs):
        return super()._deserialize(value.lower(), *args, **kwargs)


class IdentityBaseSchema(m.Schema):
    class Meta:
        unknown = m.INCLUDE

    def handle_error(self, err, data, **kwargs):
        raise ValueError(err.messages)


class IdentitySchema(IdentityBaseSchema):
    org_id = m.fields.Str(required=True, validate=m.validate.Length(min=1, max=36))
    type = m.fields.String(required=True, validate=m.validate.OneOf(IdentityType.__members__.values()))
    auth_type = IdentityLowerString(validate=m.validate.OneOf(AuthType.__members__.values()))
    account_number = m.fields.Str(validate=m.validate.Length(min=1, max=36))

    @m.post_load
    def user_system_check(self, in_data, **kwargs):
        if in_data["type"] == IdentityType.USER:
            result = UserIdentitySchema().load(in_data)
        else:
            result = SystemIdentitySchema().load(in_data)

        return result


class UserIdentitySchema(IdentityBaseSchema):
    user = m.fields.Dict()


class SystemInfoIdentitySchema(IdentityBaseSchema):
    cert_type = IdentityLowerString(required=True, validate=m.validate.OneOf(CertType.__members__.values()))
    cn = m.fields.Str(required=True)


class SystemIdentitySchema(IdentityBaseSchema):
    system = m.fields.Nested(SystemInfoIdentitySchema, required=True)


# Messages from the system_profile topic don't need to provide a real Identity,
# So this helper function creates a basic User-type identity from the host data.
def create_mock_identity_with_org_id(org_id):
    return Identity({"org_id": org_id, "type": IdentityType.USER.value, "auth_type": AuthType.BASIC})

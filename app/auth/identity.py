from __future__ import annotations

import os
from base64 import b64decode
from base64 import b64encode
from enum import Enum
from json import dumps
from json import loads
from typing import Any

import marshmallow as m

from app.logging import get_logger
from app.logging import threadctx

__all__ = ["Identity", "from_auth_header", "from_bearer_token"]

logger = get_logger(__name__)

SHARED_SECRET_ENV_VAR = "INVENTORY_SHARED_SECRET"


class AuthType(str, Enum):
    BASIC = "basic-auth"
    CERT = "cert-auth"
    JWT = "jwt-auth"
    UHC = "uhc-auth"
    SAML = "saml-auth"
    X509 = "x509"


class CertType(str, Enum):
    HYPERVISOR = "hypervisor"
    RHUI = "rhui"
    SAM = "sam"
    SATELLITE = "satellite"
    SYSTEM = "system"


class IdentityType(str, Enum):
    SYSTEM = "System"
    USER = "User"
    SERVICE_ACCOUNT = "ServiceAccount"
    ASSOCIATE = "Associate"
    X509 = "X509"


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
            if "service_account" in result:
                self.service_account = result.get("service_account")
            if "x509" in result:
                self.x509 = result.get("x509")

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
            if hasattr(self, "user"):
                ident["user"] = self.user.copy()
            return ident

        if self.identity_type == IdentityType.SYSTEM:
            ident["system"] = self.system.copy()
            return ident

        if self.identity_type == IdentityType.SERVICE_ACCOUNT:
            ident["service_account"] = self.service_account.copy()
            return ident

        if self.identity_type == IdentityType.X509:
            ident["x509"] = self.x509.copy()
            return ident

    def __eq__(self, other):
        return self.org_id == other.org_id


class IdentityLowerString(m.fields.String):
    def _deserialize(self, value, *args, **kwargs):
        return super()._deserialize(value.lower(), *args, **kwargs)


class IdentityBaseSchema(m.Schema):
    class Meta:
        unknown = m.INCLUDE

    def handle_error(self, err, data, **kwargs):  # noqa: ARG002, overrides a function from m.Schema
        raise ValueError(err.messages)


class IdentitySchema(IdentityBaseSchema):
    org_id = m.fields.Str(required=True, validate=m.validate.Length(min=1, max=36))
    type = m.fields.String(required=True, validate=m.validate.OneOf(IdentityType.__members__.values()))
    auth_type = IdentityLowerString(required=True, validate=m.validate.OneOf(AuthType.__members__.values()))
    account_number = m.fields.Str(allow_none=True, validate=m.validate.Length(min=0, max=36))

    @m.post_load
    def user_system_check(self, in_data, **kwargs):
        if in_data["type"] == IdentityType.USER:
            result = UserIdentitySchema().load(in_data)
        elif in_data["type"] == IdentityType.SYSTEM:
            result = SystemIdentitySchema().load(in_data)
        elif in_data["type"] == IdentityType.X509:
            result = X509IdentitySchema().load(in_data)
        else:
            result = ServiceAccountIdentitySchema().load(in_data)

        return result


class UserInfoIdentitySchema(IdentityBaseSchema):
    first_name = m.fields.Str()
    last_name = m.fields.Str()
    locale = m.fields.Str()
    is_active = m.fields.Bool()
    is_internal = m.fields.Bool()
    is_org_admin = m.fields.Bool()
    username = m.fields.Str()
    email = m.fields.Email()


class UserIdentitySchema(IdentityBaseSchema):
    user = m.fields.Nested(UserInfoIdentitySchema)


class SystemInfoIdentitySchema(IdentityBaseSchema):
    cert_type = IdentityLowerString(required=True, validate=m.validate.OneOf(CertType.__members__.values()))
    cn = m.fields.Str(required=True, validate=m.validate.Length(min=1))


class SystemIdentitySchema(IdentityBaseSchema):
    system = m.fields.Nested(SystemInfoIdentitySchema, required=True)


class ServiceAccountInfoIdentitySchema(IdentityBaseSchema):
    client_id = m.fields.Str(required=True, validate=m.validate.Length(min=1))
    username = m.fields.Str(required=True, validate=m.validate.Length(min=1))


class ServiceAccountIdentitySchema(IdentityBaseSchema):
    service_account = m.fields.Nested(ServiceAccountInfoIdentitySchema, required=True)


class X509InfoIdentitySchema(IdentityBaseSchema):
    subject_dn = m.fields.Str(required=True, validate=m.validate.Length(min=1))
    issuer_dn = m.fields.Str(required=True, validate=m.validate.Length(min=1))


class X509IdentitySchema(IdentityBaseSchema):
    x509 = m.fields.Nested(X509InfoIdentitySchema, required=True)


# Messages from the system_profile topic don't need to provide a real Identity,
# So this helper function creates a basic User-type identity from the host data.
def create_mock_identity_with_org_id(org_id: str) -> Identity:
    return Identity(
        {
            "org_id": org_id,
            "type": IdentityType.USER.value,
            "auth_type": AuthType.BASIC,
            "user": {"is_org_admin": False},
        }
    )


def to_auth_header(identity: Identity):
    id = {"identity": identity._asdict()}
    b64_id = b64encode(dumps(id).encode())
    return b64_id.decode("ascii")


def comes_from_rhsm(identity_dict: dict[str, Any]) -> bool:
    """
    This function determines if the API request comes from RHSM Errata service.
    If it does, the org_id can be missing from the identity header, and it is set by the
    'x-inventory-org-id' header instead.

    Here is how Prod subject_dn and issuer_dn look like for RHSM at the time of writing this function:
    subject_dn: "/O=mpaas/OU=serviceaccounts/UID=mpp:rhsm:prod-errata-notifications"
    issuer_dn: "/O=Red Hat/OU=prod/CN=2023 Certificate Authority RHCSv2"

    And here is Preprod:
    subject_dn: "/O=mpaas/OU=serviceaccounts/UID=mpp:rhsm:nonprod-errata-notifications"
    issuer_dn: "/O=Red Hat/OU=prod/CN=2023 Certificate Authority RHCSv2"
    """
    return (
        identity_dict["type"] == IdentityType.X509.value
        and identity_dict["auth_type"].lower() == AuthType.X509.value.lower()
        and "errata-notifications" in identity_dict.get("x509", {}).get("subject_dn", "")
        and "O=Red Hat" in identity_dict.get("x509", {}).get("issuer_dn", "")
    )


def from_auth_header(base64: str, org_id: str | None = None) -> Identity:
    json = b64decode(base64)
    identity_dict = loads(json)

    if comes_from_rhsm(identity_dict["identity"]) and org_id:
        identity_dict["identity"]["org_id"] = org_id

    return Identity(identity_dict["identity"])


def from_bearer_token(token):
    return Identity(token=token)

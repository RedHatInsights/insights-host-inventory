import os

from base64 import b64decode
from json import loads


__all__ = ["Identity", "IdentityBuilder", "validate"]


class IdentityBuilder:

    @staticmethod
    def from_dict(dict_):
        """
        Build an Identity from a dictionary of values.
        """
        if "account_number" not in dict_:
            # This doesn't feel like the correct thing to do here
            # but I think it matches the way it was expected to work
            # previously
            raise TypeError
        return Identity(account_number=dict_["account_number"])

    @staticmethod
    def from_json(json):
        """
        Build an Identity from a JSON string.
        """
        dict_ = loads(json)
        return IdentityBuilder.from_dict(dict_["identity"])

    @staticmethod
    def from_encoded_json(base64):
        """
        Build an Identity from the raw HTTP header value – a Base64-encoded
        JSON.
        """
        json = b64decode(base64)
        return IdentityBuilder.from_json(json)

    @staticmethod
    def from_auth_header(base64):
        if IdentityBuilder._is_authentication_disabled():
            return IdentityBuilder._build_disabled_identity()

        return IdentityBuilder.from_encoded_json(base64)

    @staticmethod
    def _is_authentication_disabled():
        return os.getenv("FLASK_DEBUG") and os.getenv("NOAUTH")

    @staticmethod
    def _build_disabled_identity():
        return Identity(account_number="0000001")

    @staticmethod
    def from_bearer_token(token):
        if IdentityBuilder._is_authentication_disabled():
            return IdentityBuilder._build_disabled_identity()

        return Identity(token=token)


class Identity:
    def __init__(self, account_number=None, token=None):
        self._is_trusted_system = False
        self._account_number = account_number

        if token:
            self.token = token
            self._is_trusted_system = True
            self._account_number = "*"

    def _asdict(self):
        return {"account_number": self._account_number}

    @property
    def account_number(self):
        return self._account_number

    @property
    def is_trusted_system(self):
        """
        A "trusted" identity is trusted to be passing in
        the correct account number(s).
        """
        return self._is_trusted_system

    def __eq__(self, other):
        return self._account_number == other._account_number


def validate(identity):
    if identity.is_trusted_system:
        if identity.token != os.getenv("INVENTORY_SHARED_SECRET"):
            raise ValueError("Invalid credentials")
    else:
        # Ensure the account number is present.
        dict_ = identity._asdict()
        if not all(dict_.values()):
            raise ValueError("The account_number is mandatory.")

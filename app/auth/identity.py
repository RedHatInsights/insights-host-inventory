import os

from base64 import b64decode
from json import loads


__all__ = ["Identity", "from_auth_header", "from_bearer_token", "validate"]


def from_auth_header(base64):
    json = b64decode(base64)
    identity_dict = loads(json)
    return Identity(**identity_dict["identity"])


def from_bearer_token(token):
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

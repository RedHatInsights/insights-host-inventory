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
    def from_bearer_token(token):
        return TrustedIdentity(token=token)


class Identity:
    def __init__(self, account_number=None):
        self._account_number = account_number

    def _asdict(self):
        return {"account_number": self._account_number}

    @property
    def account_number(self):
        return self._account_number

    def __eq__(self, other):
        print("Identity.__eq__")
        return self._account_number == other._account_number


class TrustedIdentity(Identity):
    """
    This class represents a "trusted" identity.  This
    Identity is trusted to be passing in the correct account
    number(s).
    """

    def __init__(self, token=None):
        self.token = token
        self._account_number = self.AccountNumber()

    class AccountNumber(str):
        """
        This class acts as a "wildcard" account number.
        """
        def __str__(self):
            print("AccountNumber.__str__()")
            return self.__repr__()

        def __repr__(self):
            print("AccountNumber.__repr__()")
            return "*"

        def __eq__(self, other):
            print("AccountNumber.__eq__()")
            return True

        def __ne__(self, other):
            print("AccountNumber.__ne__()")
            return False


def validate(identity):
    """
    Ensure the account number is present.
    """
    if isinstance(identity, TrustedIdentity):
        if identity.token != os.getenv("INVENTORY_SHARED_SECRET"):
            raise ValueError("Invalid credentials")
    else:
        dict_ = identity._asdict()
        if not all(dict_.values()):
            raise ValueError("The account_number is mandatory.")

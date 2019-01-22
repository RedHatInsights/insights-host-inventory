from base64 import b64decode
from collections import namedtuple
from json import loads


__all__ = ["Identity", "from_dict", "from_json", "from_encoded", "validate"]


Identity = namedtuple("Identity", ("account_number"))


def from_dict(dict_):
    """
    Build an Identity from a dictionary of values.
    """
    if "account_number" not in dict_:
        # This doesn't feel like the correct thing to do here
        # but I think it matches the way it was expected to work
        # previously
        raise TypeError("'account_number'")
    return Identity(account_number=dict_["account_number"])


def from_json(json):
    """
    Build an Identity from a JSON string.
    """
    dict_ = loads(json)
    return from_dict(dict_["identity"])


def from_encoded(base64):
    """
    Build an Identity from the raw HTTP header value – a Base64-encoded
    JSON.
    """
    json = b64decode(base64)
    return from_json(json)


def validate(identity):
    """
    Ensure both values are present.
    """
    dict_ = identity._asdict()
    if not all(dict_.values()):
        raise ValueError("The account_number is mandatory.")

from base64 import b64decode
from collections import namedtuple
from json import loads


__all__ = ["Identity",
           "from_dict",
           "from_json",
           "from_encoded",
           "validate"]


Identity = namedtuple("Identity", ("account_number", "org_id"))


def from_dict(dict_):
    """
    Build an Identity from a dictionary of values.
    """
    return Identity(**dict_)


def from_json(json):
    """
    Build an Identity from a JSON string.
    """
    dict_ = loads(json)
    return from_dict(dict_)


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
        raise ValueError("Both account_number and org_id are mandatory.")

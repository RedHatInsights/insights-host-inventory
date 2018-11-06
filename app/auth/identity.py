__all__ = ["from_encoded", "validate"]


def from_encoded(payload):
    """
    Encoded payload parser stub. Just returns what it gets – the raw data. Will convert
    the data from an encoded string to an Identity object instance.
    """
    return payload


def validate(identity):
    """
    Validation method stub: considers the identity valid if it contains any non-empty
    data.
    """
    if not identity:
        raise ValueError

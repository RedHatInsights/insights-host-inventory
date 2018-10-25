class Identity:
    """
    Identity data struct stub. Only stores what it receives.
    """
    def __init__(self, auth_data):
        self.auth_data = auth_data


def from_http_header(base64):
    """
    HTTP header parser stub. Just creates an Identity instance with the
    given raw HTTP header data.
    """
    return Identity(base64)


def validate(identity):
    """
    Validation method stub: considers the identity valid if it contains
    any non-empty data.
    """
    if not identity.auth_data:
        raise ValueError

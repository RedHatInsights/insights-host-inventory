from base64 import b64encode
from json import dumps

from app.auth.identity import Identity
from tests.helpers.api_utils import build_token_auth_header
from tests.helpers.api_utils import HOST_URL
from tests.helpers.api_utils import SYSTEM_IDENTITY
from tests.helpers.api_utils import USER_IDENTITY


def valid_identity(identity_type):
    """
    Provides a valid Identity object.
    """
    if identity_type == "User":
        return Identity(USER_IDENTITY)
    else:
        return Identity(SYSTEM_IDENTITY)


def valid_payload(identity_type):
    """
    Builds a valid HTTP header payload – Base64 encoded JSON string with valid data.
    """
    identity = valid_identity(identity_type)
    dict_ = {"identity": identity._asdict()}
    json = dumps(dict_)
    return b64encode(json.encode())


def test_validate_missing_identity(flask_client):
    """
    Identity header is not present.
    """
    response = flask_client.get(HOST_URL, headers={})
    assert 401 == response.status_code


def test_validate_invalid_identity(flask_client):
    """
    Identity header is not valid – empty in this case
    """
    response = flask_client.get(HOST_URL, headers={"x-rh-identity": ""})
    assert 401 == response.status_code


def test_validate_valid_user_identity(flask_client):
    """
    Identity header is valid – non-empty in this case
    """
    payload = valid_payload("User")
    response = flask_client.get(HOST_URL, headers={"x-rh-identity": payload})
    assert 200 == response.status_code  # OK


def test_validate_valid_system_identity(flask_client):
    """
    Identity header is valid – non-empty in this case
    """
    payload = valid_payload("System")
    response = flask_client.get(HOST_URL, headers={"x-rh-identity": payload})
    assert 200 == response.status_code  # OK


def test_validate_invalid_token_on_get(flask_client):
    auth_header = build_token_auth_header("NotTheSuperSecretValue")
    response = flask_client.get(HOST_URL, headers=auth_header)
    assert 401 == response.status_code

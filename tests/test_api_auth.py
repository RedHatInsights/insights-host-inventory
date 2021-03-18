from base64 import b64encode
from json import dumps

from app.auth.identity import Identity
from tests.helpers.api_utils import build_token_auth_header
from tests.helpers.api_utils import HOST_URL
from tests.helpers.api_utils import SYSTEM_PROFILE_URL
from tests.helpers.test_utils import INSIGHTS_CLASSIC_IDENTITY
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import USER_IDENTITY


def invalid_identities(identity_type):
    if identity_type == "System":
        no_cert_type = Identity(SYSTEM_IDENTITY)._asdict()
        no_cert_type["system"].pop("cert_type", None)

        no_cn = Identity(SYSTEM_IDENTITY)._asdict()
        no_cn["system"].pop("cn", None)

        no_system = Identity(SYSTEM_IDENTITY)._asdict()
        no_system.pop("system", None)

        return (no_cert_type, no_cn, no_system)


def invalid_payloads(identity_type):
    if identity_type == "System":
        payloads = ()
        for identity in invalid_identities("System"):
            dict_ = {"identity": identity}
            json = dumps(dict_)
            payloads += (b64encode(json.encode()),)
        return payloads


def valid_identity(identity_type):
    """
    Provides a valid Identity object.
    """
    if identity_type == "User":
        return Identity(USER_IDENTITY)
    elif identity_type == "System":
        return Identity(SYSTEM_IDENTITY)


def create_identity_payload(identity):
    dict_ = {"identity": identity._asdict()}
    json = dumps(dict_)
    return b64encode(json.encode())


def valid_payload(identity_type):
    """
    Builds a valid HTTP header payload – Base64 encoded JSON string with valid data.
    """
    identity = valid_identity(identity_type)
    return create_identity_payload(identity)


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


def test_validate_non_admin_user_identity(flask_client):
    """
    Identity header is valid and user is provided, but is not an Admin
    """
    identity = valid_identity("User")
    identity.user["username"] = "regularjoe@redhat.com"
    payload = create_identity_payload(identity)
    response = flask_client.post(
        f"{SYSTEM_PROFILE_URL}/validate_schema?repo_branch=master&days=1", headers={"x-rh-identity": payload}
    )
    assert 403 == response.status_code  # User is not an HBI admin


def test_validate_non_user_admin_endpoint(flask_client):
    """
    Identity header is valid and user is provided, but is not an Admin
    """
    payload = valid_payload("System")
    response = flask_client.post(
        f"{SYSTEM_PROFILE_URL}/validate_schema?repo_branch=master&days=1", headers={"x-rh-identity": payload}
    )
    assert 403 == response.status_code  # Endpoint not available to Systems


def test_validate_valid_system_identity(flask_client):
    """
    Identity header is valid – non-empty in this case
    """
    payload = valid_payload("System")
    response = flask_client.get(HOST_URL, headers={"x-rh-identity": payload})
    assert 200 == response.status_code  # OK


def test_invalid_system_identities(flask_client, subtests):
    payloads = invalid_payloads("System")

    for payload in payloads:
        with subtests.test():
            response = flask_client.get(HOST_URL, headers={"x-rh-identity": payload})
            assert 401 == response.status_code  # Bad identity


def test_insights_classic_workaround(flask_client):
    payload = create_identity_payload(Identity(INSIGHTS_CLASSIC_IDENTITY))
    response = flask_client.get(HOST_URL, headers={"x-rh-identity": payload})
    assert 200 == response.status_code  # OK


# This one can likely be removed when the insights classic workaround is
# no longer needed
def test_validate_valid_user_identity_no_auth_type(flask_client):
    """
    Identity header is valid – non-empty in this case
    """
    identity_dict = valid_identity("User")._asdict()
    identity_dict.pop("auth_type")
    dict_ = {"identity": identity_dict}
    json = dumps(dict_)
    payload = b64encode(json.encode())

    response = flask_client.get(HOST_URL, headers={"x-rh-identity": payload})
    assert 200 == response.status_code  # OK


def test_validate_invalid_token_on_get(flask_client):
    auth_header = build_token_auth_header("NotTheSuperSecretValue")
    response = flask_client.get(HOST_URL, headers=auth_header)
    assert 401 == response.status_code

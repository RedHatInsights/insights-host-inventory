from base64 import b64encode
from copy import deepcopy
from json import dumps

import pytest

from app.auth.identity import Identity
from app.auth.identity import IdentityType
from tests.helpers.api_utils import build_token_auth_header
from tests.helpers.api_utils import HOST_URL
from tests.helpers.api_utils import SYSTEM_PROFILE_URL
from tests.helpers.test_utils import SERVICE_ACCOUNT_IDENTITY
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import USER_IDENTITY


def invalid_identities(identity_type):
    if identity_type == IdentityType.SYSTEM:
        no_cert_type = Identity(SYSTEM_IDENTITY)._asdict()
        no_cert_type["system"].pop("cert_type", None)

        no_cn = Identity(SYSTEM_IDENTITY)._asdict()
        no_cn["system"].pop("cn", None)

        no_system = Identity(SYSTEM_IDENTITY)._asdict()
        no_system.pop("system", None)

        return (no_cert_type, no_cn, no_system)


def invalid_payloads(identity_type):
    if identity_type == IdentityType.SYSTEM:
        payloads = ()
        for identity in invalid_identities(IdentityType.SYSTEM):
            dict_ = {"identity": identity}
            json = dumps(dict_)
            payloads += (b64encode(json.encode()),)
        return payloads


def create_identity_payload(identity):
    # Load into Identity object for validation, then return to dict
    dict_ = {"identity": Identity(identity)._asdict()}
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


@pytest.mark.parametrize(
    "remove_account_number, identity",
    ((True, USER_IDENTITY), (False, USER_IDENTITY), (False, SERVICE_ACCOUNT_IDENTITY)),
)
def test_validate_valid_identity(flask_client, remove_account_number, identity):
    """
    Identity header is valid – non-empty in this case
    """
    identity = deepcopy(identity)
    if remove_account_number:
        del identity["account_number"]

    payload = create_identity_payload(identity)
    response = flask_client.get(HOST_URL, headers={"x-rh-identity": payload})
    assert 200 == response.status_code  # OK


def test_validate_non_admin_user_identity(flask_client):
    """
    Identity header is valid and user is provided, but is not an Admin
    """
    identity = deepcopy(USER_IDENTITY)
    identity["user"]["username"] = "regularjoe@redhat.com"
    payload = create_identity_payload(identity)
    response = flask_client.post(
        f"{SYSTEM_PROFILE_URL}/validate_schema?repo_branch=master&days=1", headers={"x-rh-identity": payload}
    )
    assert 403 == response.status_code  # User is not an HBI admin


def test_validate_non_admin_service_account_identity(flask_client):
    """
    Identity header is valid and service account is provided, but is not an Admin
    """
    identity = deepcopy(SERVICE_ACCOUNT_IDENTITY)
    identity["service_account"]["username"] = "regularjoe@redhat.com"
    payload = create_identity_payload(identity)
    response = flask_client.post(
        f"{SYSTEM_PROFILE_URL}/validate_schema?repo_branch=master&days=1", headers={"x-rh-identity": payload}
    )
    assert 403 == response.status_code  # User is not an HBI admin


def test_validate_non_user_admin_endpoint(flask_client):
    """
    Identity header is valid and system is provided, but is not an Admin
    """
    payload = create_identity_payload(SYSTEM_IDENTITY)
    response = flask_client.post(
        f"{SYSTEM_PROFILE_URL}/validate_schema?repo_branch=master&days=1", headers={"x-rh-identity": payload}
    )
    assert 403 == response.status_code  # Endpoint not available to Systems


def test_validate_valid_system_identity(flask_client):
    """
    Identity header is valid – non-empty in this case
    """
    payload = create_identity_payload(SYSTEM_IDENTITY)
    response = flask_client.get(HOST_URL, headers={"x-rh-identity": payload})
    assert 200 == response.status_code  # OK


def test_validate_service_account_admin_endpoint(flask_client):
    """
    Identity header is valid and service account is provided, but is not an Admin
    """
    payload = create_identity_payload(SERVICE_ACCOUNT_IDENTITY)
    response = flask_client.post(
        f"{SYSTEM_PROFILE_URL}/validate_schema?repo_branch=master&days=1", headers={"x-rh-identity": payload}
    )
    assert 403 == response.status_code  # Endpoint not available to Service accounts


def test_invalid_system_identities(flask_client, subtests):
    payloads = invalid_payloads(IdentityType.SYSTEM)

    for payload in payloads:
        with subtests.test():
            response = flask_client.get(HOST_URL, headers={"x-rh-identity": payload})
            assert 401 == response.status_code  # Bad identity


def test_validate_invalid_token_on_get(flask_client):
    auth_header = build_token_auth_header("NotTheSuperSecretValue")
    response = flask_client.get(HOST_URL, headers=auth_header)
    assert 401 == response.status_code

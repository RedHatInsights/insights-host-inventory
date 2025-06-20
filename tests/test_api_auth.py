from __future__ import annotations

from base64 import b64encode
from copy import deepcopy
from json import dumps
from typing import Any

import pytest
from pytest_subtests import SubTests
from starlette.testclient import TestClient

from app import process_identity_header
from app.auth.identity import Identity
from app.auth.identity import IdentityType
from tests.helpers.api_utils import HOST_URL
from tests.helpers.api_utils import SYSTEM_PROFILE_URL
from tests.helpers.api_utils import build_token_auth_header
from tests.helpers.test_utils import SERVICE_ACCOUNT_IDENTITY
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import X509_IDENTITY


def invalid_identities(identity_type: IdentityType) -> list[dict[str, Any]]:
    identities = []

    if identity_type == IdentityType.SYSTEM:
        base_identity = Identity(SYSTEM_IDENTITY)._asdict()

        no_cert_type = deepcopy(base_identity)
        no_cert_type["system"].pop("cert_type")

        no_cn = deepcopy(base_identity)
        no_cn["system"].pop("cn")

        no_system = deepcopy(base_identity)
        no_system.pop("system")

        identities += [no_cert_type, no_cn, no_system]

    if identity_type == IdentityType.SERVICE_ACCOUNT:
        base_identity = Identity(SERVICE_ACCOUNT_IDENTITY)._asdict()

        no_client_id = deepcopy(base_identity)
        no_client_id["service_account"].pop("client_id")

        no_username = deepcopy(base_identity)
        no_username["service_account"].pop("username")

        no_service_account = deepcopy(base_identity)
        no_service_account.pop("service_account")

        identities += [no_client_id, no_username, no_service_account]

    if identity_type == IdentityType.X509:
        base_identity = Identity(X509_IDENTITY)._asdict()

        no_subject_dn = deepcopy(base_identity)
        no_subject_dn["x509"].pop("subject_dn")

        no_issuer_dn = deepcopy(base_identity)
        no_issuer_dn["x509"].pop("issuer_dn")

        no_x509 = deepcopy(base_identity)
        no_x509.pop("x509")

        identities += [no_subject_dn, no_issuer_dn, no_x509]

    else:
        base_identity = Identity(USER_IDENTITY)._asdict()

    no_org_id = deepcopy(base_identity)
    no_org_id.pop("org_id")

    no_type = deepcopy(base_identity)
    no_type.pop("type")

    no_auth_type = deepcopy(base_identity)
    no_auth_type.pop("auth_type")

    return identities + [no_org_id, no_type, no_auth_type]


def invalid_payloads(identity_type: IdentityType) -> tuple[bytes, ...]:
    payloads: tuple[bytes, ...] = ()
    for identity in invalid_identities(identity_type):
        dict_ = {"identity": identity}
        json = dumps(dict_)
        payloads += (b64encode(json.encode()),)
    return payloads


def create_identity_payload(identity: dict[str, Any]) -> bytes:
    # Load into Identity object for validation, then return to dict
    dict_ = {"identity": Identity(identity)._asdict()}
    json = dumps(dict_)
    return b64encode(json.encode())


def test_validate_missing_identity(flask_client: TestClient):
    """
    Identity header is not present.
    """
    response = flask_client.get(HOST_URL, headers={})
    assert response.status_code == 401


def test_validate_empty_identity(flask_client: TestClient):
    """
    Identity header is not valid – empty in this case
    """
    response = flask_client.get(HOST_URL, headers={"x-rh-identity": ""})
    assert response.status_code == 401


@pytest.mark.parametrize("remove_account_number", (True, False))
@pytest.mark.parametrize(
    "identity",
    (USER_IDENTITY, SYSTEM_IDENTITY, SERVICE_ACCOUNT_IDENTITY),
    ids=("user", "system", "service-account"),
)
def test_validate_valid_identity(flask_client: TestClient, remove_account_number: bool, identity: dict[str, Any]):
    """
    Identity header is valid – non-empty in this case
    """
    test_identity = deepcopy(identity)
    if remove_account_number:
        test_identity.pop("account_number", None)

    payload = create_identity_payload(test_identity)
    response = flask_client.get(HOST_URL, headers={"x-rh-identity": payload})
    assert response.status_code == 200  # OK


@pytest.mark.parametrize(
    "identity",
    (USER_IDENTITY, SYSTEM_IDENTITY, SERVICE_ACCOUNT_IDENTITY),
    ids=("user", "system", "service-account"),
)
def test_validate_non_admin_identity(flask_client: TestClient, identity: dict[str, Any]):
    """
    Identity header is valid, but is not an Admin
    """
    test_identity = deepcopy(identity)
    if "user" in test_identity:
        test_identity["user"]["username"] = "regularjoe@redhat.com"
    payload = create_identity_payload(test_identity)
    response = flask_client.post(
        f"{SYSTEM_PROFILE_URL}/validate_schema?repo_branch=master&days=1", headers={"x-rh-identity": payload}
    )
    assert response.status_code == 403  # User is not an HBI admin


@pytest.mark.parametrize("identity_type", (IdentityType.USER, IdentityType.SYSTEM, IdentityType.SERVICE_ACCOUNT))
def test_validate_invalid_identity(flask_client: TestClient, subtests: SubTests, identity_type: IdentityType):
    payloads = invalid_payloads(identity_type)

    for payload in payloads:
        with subtests.test():
            response = flask_client.get(HOST_URL, headers={"x-rh-identity": payload})
            assert response.status_code == 401  # Bad identity


def test_validate_invalid_token_on_get(flask_client: TestClient):
    auth_header = build_token_auth_header("NotTheSuperSecretValue")
    response = flask_client.get(HOST_URL, headers=auth_header)
    assert response.status_code == 401


def test_invalid_system_identities_processing():
    no_system = Identity(SYSTEM_IDENTITY)._asdict()
    no_system.pop("system", None)
    dict_ = {"identity": no_system}
    json = dumps(dict_)
    identity_payload = b64encode(json.encode())
    with pytest.raises(Exception):  # noqa: B017
        process_identity_header(identity_payload)


def test_valid_system_identities_processing():
    system = Identity(SYSTEM_IDENTITY)._asdict()
    dict_ = {"identity": system}
    json = dumps(dict_)
    identity_payload = b64encode(json.encode())
    org_id, access_id = process_identity_header(identity_payload)
    assert org_id == system.get("org_id")
    assert access_id == system.get("system", {}).get("cn")

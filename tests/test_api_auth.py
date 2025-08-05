from __future__ import annotations

from base64 import b64encode
from collections.abc import Callable
from copy import deepcopy
from json import dumps
from typing import Any

import pytest
from pytest_subtests import SubTests
from starlette.testclient import TestClient

from app import process_identity_header
from app.auth.identity import Identity
from app.auth.identity import IdentityType
from app.models import Host
from tests.helpers.api_utils import HOST_URL
from tests.helpers.api_utils import SYSTEM_PROFILE_URL
from tests.helpers.api_utils import build_token_auth_header
from tests.helpers.test_utils import RHSM_ERRATA_IDENTITY_PROD
from tests.helpers.test_utils import RHSM_ERRATA_IDENTITY_STAGE
from tests.helpers.test_utils import SERVICE_ACCOUNT_IDENTITY
from tests.helpers.test_utils import SYSTEM_IDENTITY
from tests.helpers.test_utils import USER_IDENTITY
from tests.helpers.test_utils import X509_IDENTITY
from tests.helpers.test_utils import generate_uuid


def invalid_identities(identity_type: IdentityType) -> list[dict[str, Any]]:
    identities = []

    if identity_type == IdentityType.SYSTEM:
        base_identity = deepcopy(SYSTEM_IDENTITY)

        no_cert_type = deepcopy(base_identity)
        no_cert_type["system"].pop("cert_type")

        no_cn = deepcopy(base_identity)
        no_cn["system"].pop("cn")

        no_system = deepcopy(base_identity)
        no_system.pop("system")

        identities += [no_cert_type, no_cn, no_system]

    if identity_type == IdentityType.SERVICE_ACCOUNT:
        base_identity = deepcopy(SERVICE_ACCOUNT_IDENTITY)

        no_client_id = deepcopy(base_identity)
        no_client_id["service_account"].pop("client_id")

        no_username = deepcopy(base_identity)
        no_username["service_account"].pop("username")

        no_service_account = deepcopy(base_identity)
        no_service_account.pop("service_account")

        identities += [no_client_id, no_username, no_service_account]

    if identity_type == IdentityType.X509:
        base_identity = deepcopy(X509_IDENTITY)
        base_identity["org_id"] = "test"

        no_subject_dn = deepcopy(base_identity)
        no_subject_dn["x509"].pop("subject_dn")

        no_issuer_dn = deepcopy(base_identity)
        no_issuer_dn["x509"].pop("issuer_dn")

        no_x509 = deepcopy(base_identity)
        no_x509.pop("x509")

        identities += [no_subject_dn, no_issuer_dn, no_x509]

    else:
        base_identity = deepcopy(USER_IDENTITY)

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
    test_identity = deepcopy(identity)
    if remove_account_number:
        test_identity.pop("account_number", None)

    payload = create_identity_payload(test_identity)
    response = flask_client.get(HOST_URL, headers={"x-rh-identity": payload})
    assert response.status_code == 200  # OK


def test_validate_x509_non_rhsm_identity_with_org_id(flask_client: TestClient):
    """
    X509 Identity header is valid and includes org_id
    """
    test_identity = deepcopy(X509_IDENTITY)
    test_identity["org_id"] = "test"

    payload = create_identity_payload(test_identity)
    response = flask_client.get(HOST_URL, headers={"x-rh-identity": payload})
    assert response.status_code == 200  # OK


def test_validate_x509_non_rhsm_identity_without_org_id(flask_client: TestClient):
    """
    Non-RHSM X509 Identity header that doesn't include org_id
    """
    test_identity = deepcopy(X509_IDENTITY)
    json = dumps({"identity": test_identity})
    payload = b64encode(json.encode())

    response = flask_client.get(HOST_URL, headers={"x-rh-identity": payload})
    assert response.status_code == 401  # Missing org_id


def test_validate_x509_non_rhsm_identity_without_org_id_with_org_id_header(flask_client: TestClient):
    """
    Non-RHSM X509 Identity header that doesn't include org_id and is sent together with org_id header
    """
    test_identity = deepcopy(X509_IDENTITY)
    json = dumps({"identity": test_identity})
    payload = b64encode(json.encode())

    response = flask_client.get(HOST_URL, headers={"x-rh-identity": payload, "x-inventory-org-id": "test"})
    assert response.status_code == 401  # Missing org_id


def test_validate_x509_rhsm_identity_with_org_id(flask_client: TestClient):
    """
    X509 Identity header from RHSM Errata that includes org_id
    """
    test_identity = deepcopy(RHSM_ERRATA_IDENTITY_PROD)
    test_identity["org_id"] = "test"
    payload = create_identity_payload(test_identity)

    response = flask_client.get(HOST_URL, headers={"x-rh-identity": payload})
    assert response.status_code == 200  # OK


def test_validate_x509_rhsm_identity_without_org_id(flask_client: TestClient):
    """
    X509 Identity header from RHSM Errata that doesn't include org_id
    """
    test_identity = deepcopy(RHSM_ERRATA_IDENTITY_PROD)
    json = dumps({"identity": test_identity})
    payload = b64encode(json.encode())

    response = flask_client.get(HOST_URL, headers={"x-rh-identity": payload})
    assert response.status_code == 401  # Missing org_id


def test_validate_x509_rhsm_identity_without_org_id_with_org_id_header(flask_client: TestClient):
    """
    X509 Identity header from RHSM Errata that doesn't include org_id, but is sent together with org_id header
    """
    test_identity = deepcopy(RHSM_ERRATA_IDENTITY_PROD)
    json = dumps({"identity": test_identity})
    payload = b64encode(json.encode())

    response = flask_client.get(HOST_URL, headers={"x-rh-identity": payload, "x-inventory-org-id": "test"})
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


def test_validate_non_admin_identity_x509(flask_client: TestClient):
    """
    X509 Identity header is valid, but is not an Admin
    """
    test_identity = deepcopy(X509_IDENTITY)
    test_identity["org_id"] = "test"

    payload = create_identity_payload(test_identity)
    response = flask_client.post(
        f"{SYSTEM_PROFILE_URL}/validate_schema?repo_branch=master&days=1", headers={"x-rh-identity": payload}
    )
    assert response.status_code == 403  # User is not an HBI admin


@pytest.mark.parametrize(
    "identity_type", (IdentityType.USER, IdentityType.SYSTEM, IdentityType.SERVICE_ACCOUNT, IdentityType.X509)
)
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


@pytest.mark.parametrize(
    "identity",
    (USER_IDENTITY, SERVICE_ACCOUNT_IDENTITY, X509_IDENTITY),
    ids=("user", "service-account", "X509"),
)
def test_access_non_rhsm_identity_with_org_id_header(
    db_create_host: Callable[..., Host],
    api_get: Callable[..., tuple[int, dict]],
    identity: dict[str, Any],
):
    """
    Test that org_id header is ignored if we use other than RHSM X509 identity
    """
    host_id = str(db_create_host(extra_data={"org_id": "test"}).id)
    db_create_host(extra_data={"org_id": "12345"})  # Create a host in a different org

    tested_identity = deepcopy(identity)
    tested_identity["org_id"] = "test"
    response_status, response_data = api_get(
        HOST_URL, identity=tested_identity, extra_headers={"x-inventory-org-id": "12345"}
    )
    assert response_status == 200
    assert len(response_data["results"]) >= 1

    found = False
    for response_host in response_data["results"]:
        # Verify that the x-inventory-org-id header was ignored
        assert response_host["org_id"] == "test"
        if response_host["id"] == host_id:
            found = True
    assert found


def test_access_system_identity_with_org_id_header(
    db_create_host: Callable[..., Host],
    api_get: Callable[..., tuple[int, dict]],
):
    """
    Test that org_id header is ignored if we use system identity
    """
    cn = generate_uuid()
    host_id = str(db_create_host(extra_data={"org_id": "test", "system_profile_facts": {"owner_id": cn}}).id)
    db_create_host(
        extra_data={"org_id": "12345", "system_profile_facts": {"owner_id": cn}}  # Create a host in a different org
    )

    tested_identity = deepcopy(SYSTEM_IDENTITY)
    tested_identity["org_id"] = "test"
    tested_identity["system"]["cn"] = cn
    response_status, response_data = api_get(
        HOST_URL, identity=tested_identity, extra_headers={"x-inventory-org-id": "12345"}
    )
    assert response_status == 200
    assert len(response_data["results"]) >= 1

    found = False
    for response_host in response_data["results"]:
        # Verify that the x-inventory-org-id header was ignored
        assert response_host["org_id"] == "test"
        if response_host["id"] == host_id:
            found = True
    assert found


@pytest.mark.parametrize("identity", (RHSM_ERRATA_IDENTITY_PROD, RHSM_ERRATA_IDENTITY_STAGE), ids=("prod", "stage"))
@pytest.mark.parametrize("with_org_id", (True, False))
def test_access_rhsm_identity_with_org_id_header(
    db_create_host: Callable[..., Host],
    api_get: Callable[..., tuple[int, dict]],
    identity: dict[str, Any],
    with_org_id: bool,
):
    """
    This that org_id header is applied if we use RHSM X509 identity
    """
    host_id = str(db_create_host(extra_data={"org_id": "test"}).id)
    db_create_host(extra_data={"org_id": "12345"})  # Create a host in a different org

    tested_identity = deepcopy(identity)
    if with_org_id:
        tested_identity["org_id"] = "12345"
    response_status, response_data = api_get(
        HOST_URL, identity=tested_identity, extra_headers={"x-inventory-org-id": "test"}
    )
    assert response_status == 200
    assert len(response_data["results"]) >= 1

    found = False
    for response_host in response_data["results"]:
        # Verify that the x-inventory-org-id header was ignored
        assert response_host["org_id"] == "test"
        if response_host["id"] == host_id:
            found = True
    assert found

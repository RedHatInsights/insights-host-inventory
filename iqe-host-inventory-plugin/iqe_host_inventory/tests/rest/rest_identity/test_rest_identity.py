import json
import logging
from collections.abc import Generator
from copy import deepcopy

import pytest
from dynaconf.utils.boxing import DynaBox
from iqe.base.application import Application
from iqe.base.auth import AuthType
from pytest_lazy_fixtures import lf

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory_api import ApiException

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.backend]


@pytest.fixture(params=["basic-auth", "jwt-auth"])
def host_inventory_user_correct(
    request, application: Application, hbi_identity_auth_user: DynaBox
) -> Generator[ApplicationHostInventory, None, None]:
    user = deepcopy(hbi_identity_auth_user)
    user.identity.auth_type = request.param
    with application.copy_using(auth_type=AuthType.IDENTITY, user=user, verify_ssl=False) as app:
        yield app.host_inventory


@pytest.fixture(
    params=[
        pytest.param(lf("hbi_identity_auth_user"), id="user"),
        pytest.param(lf("hbi_identity_auth_system"), id="system"),
        pytest.param(lf("hbi_identity_auth_service_account"), id="service_account"),
    ]
)
def rest_correct_identity(request) -> DynaBox:
    return deepcopy(request.param)


@pytest.fixture()
def host_inventory_blank_org_id(
    rest_correct_identity: DynaBox, application: Application
) -> Generator[ApplicationHostInventory, None, None]:
    user = deepcopy(rest_correct_identity)
    user.identity.org_id = ""
    with application.copy_using(auth_type=AuthType.IDENTITY, user=user, verify_ssl=False) as app:
        yield app.host_inventory


@pytest.fixture()
def host_inventory_without_org_id(
    rest_correct_identity: DynaBox, application: Application
) -> Generator[ApplicationHostInventory, None, None]:
    user = deepcopy(rest_correct_identity)
    del user.identity.org_id
    with application.copy_using(auth_type=AuthType.IDENTITY, user=user, verify_ssl=False) as app:
        yield app.host_inventory


@pytest.fixture()
def host_inventory_invalid_type(
    rest_correct_identity: DynaBox, application: Application
) -> Generator[ApplicationHostInventory, None, None]:
    user = deepcopy(rest_correct_identity)
    user.identity.type = "Invalid"
    with application.copy_using(auth_type=AuthType.IDENTITY, user=user, verify_ssl=False) as app:
        yield app.host_inventory


@pytest.fixture()
def host_inventory_blank_type(
    rest_correct_identity: DynaBox, application: Application
) -> Generator[ApplicationHostInventory, None, None]:
    user = deepcopy(rest_correct_identity)
    user.identity.type = ""
    with application.copy_using(auth_type=AuthType.IDENTITY, user=user, verify_ssl=False) as app:
        yield app.host_inventory


@pytest.fixture()
def host_inventory_without_type(
    rest_correct_identity: DynaBox, application: Application
) -> Generator[ApplicationHostInventory, None, None]:
    user = deepcopy(rest_correct_identity)
    del user.identity.type
    with application.copy_using(auth_type=AuthType.IDENTITY, user=user, verify_ssl=False) as app:
        yield app.host_inventory


@pytest.fixture(params=["invalid-auth", "classic-proxy"])
def host_inventory_invalid_auth_type(
    request, rest_correct_identity: DynaBox, application: Application
) -> Generator[ApplicationHostInventory, None, None]:
    user = deepcopy(rest_correct_identity)
    user.identity.auth_type = request.param
    with application.copy_using(auth_type=AuthType.IDENTITY, user=user, verify_ssl=False) as app:
        yield app.host_inventory


@pytest.fixture()
def host_inventory_blank_auth_type(
    rest_correct_identity: DynaBox, application: Application
) -> Generator[ApplicationHostInventory, None, None]:
    user = deepcopy(rest_correct_identity)
    user.identity.auth_type = ""
    with application.copy_using(auth_type=AuthType.IDENTITY, user=user, verify_ssl=False) as app:
        yield app.host_inventory


@pytest.fixture()
def host_inventory_without_auth_type(
    rest_correct_identity: DynaBox, application: Application
) -> Generator[ApplicationHostInventory, None, None]:
    user = deepcopy(rest_correct_identity)
    del user.identity.auth_type
    with application.copy_using(auth_type=AuthType.IDENTITY, user=user, verify_ssl=False) as app:
        yield app.host_inventory


@pytest.fixture()
def host_inventory_system_blank_cn(
    hbi_identity_auth_system: DynaBox, application: Application
) -> Generator[ApplicationHostInventory, None, None]:
    user = deepcopy(hbi_identity_auth_system)
    user.identity.system.cn = ""
    with application.copy_using(auth_type=AuthType.IDENTITY, user=user, verify_ssl=False) as app:
        yield app.host_inventory


@pytest.fixture()
def host_inventory_system_without_cn(
    hbi_identity_auth_system: DynaBox, application: Application
) -> Generator[ApplicationHostInventory, None, None]:
    user = deepcopy(hbi_identity_auth_system)
    del user.identity.system.cn
    with application.copy_using(auth_type=AuthType.IDENTITY, user=user, verify_ssl=False) as app:
        yield app.host_inventory


@pytest.fixture()
def host_inventory_system_invalid_cert_type(
    hbi_identity_auth_system: DynaBox, application: Application
) -> Generator[ApplicationHostInventory, None, None]:
    user = deepcopy(hbi_identity_auth_system)
    user.identity.system.cert_type = "invalid"
    with application.copy_using(auth_type=AuthType.IDENTITY, user=user, verify_ssl=False) as app:
        yield app.host_inventory


@pytest.fixture()
def host_inventory_system_blank_cert_type(
    hbi_identity_auth_system: DynaBox, application: Application
) -> Generator[ApplicationHostInventory, None, None]:
    user = deepcopy(hbi_identity_auth_system)
    user.identity.system.cert_type = ""
    with application.copy_using(auth_type=AuthType.IDENTITY, user=user, verify_ssl=False) as app:
        yield app.host_inventory


@pytest.fixture()
def host_inventory_system_without_cert_type(
    hbi_identity_auth_system: DynaBox, application: Application
) -> Generator[ApplicationHostInventory, None, None]:
    user = deepcopy(hbi_identity_auth_system)
    del user.identity.system.cert_type
    with application.copy_using(auth_type=AuthType.IDENTITY, user=user, verify_ssl=False) as app:
        yield app.host_inventory


@pytest.fixture()
def host_inventory_system_blank_system(
    hbi_identity_auth_system: DynaBox, application: Application
) -> Generator[ApplicationHostInventory, None, None]:
    user = deepcopy(hbi_identity_auth_system)
    del user.identity.system.cert_type
    del user.identity.system.cn
    with application.copy_using(auth_type=AuthType.IDENTITY, user=user, verify_ssl=False) as app:
        yield app.host_inventory


@pytest.fixture()
def host_inventory_system_without_system(
    hbi_identity_auth_system: DynaBox, application: Application
) -> Generator[ApplicationHostInventory, None, None]:
    user = deepcopy(hbi_identity_auth_system)
    del user.identity.system
    with application.copy_using(auth_type=AuthType.IDENTITY, user=user, verify_ssl=False) as app:
        yield app.host_inventory


@pytest.fixture()
def host_inventory_service_account_blank_client_id(
    hbi_identity_auth_service_account: DynaBox, application: Application
) -> Generator[ApplicationHostInventory, None, None]:
    user = deepcopy(hbi_identity_auth_service_account)
    user.identity.service_account.client_id = ""
    with application.copy_using(auth_type=AuthType.IDENTITY, user=user, verify_ssl=False) as app:
        yield app.host_inventory


@pytest.fixture()
def host_inventory_service_account_without_client_id(
    hbi_identity_auth_service_account: DynaBox, application: Application
) -> Generator[ApplicationHostInventory, None, None]:
    user = deepcopy(hbi_identity_auth_service_account)
    del user.identity.service_account.client_id
    with application.copy_using(auth_type=AuthType.IDENTITY, user=user, verify_ssl=False) as app:
        yield app.host_inventory


@pytest.fixture()
def host_inventory_service_account_blank_username(
    hbi_identity_auth_service_account: DynaBox, application: Application
) -> Generator[ApplicationHostInventory, None, None]:
    user = deepcopy(hbi_identity_auth_service_account)
    user.identity.service_account.username = ""
    with application.copy_using(auth_type=AuthType.IDENTITY, user=user, verify_ssl=False) as app:
        yield app.host_inventory


@pytest.fixture()
def host_inventory_service_account_without_username(
    hbi_identity_auth_service_account: DynaBox, application: Application
) -> Generator[ApplicationHostInventory, None, None]:
    user = deepcopy(hbi_identity_auth_service_account)
    del user.identity.service_account.username
    with application.copy_using(auth_type=AuthType.IDENTITY, user=user, verify_ssl=False) as app:
        yield app.host_inventory


@pytest.fixture()
def host_inventory_service_account_blank_service_account(
    hbi_identity_auth_service_account: DynaBox, application: Application
) -> Generator[ApplicationHostInventory, None, None]:
    user = deepcopy(hbi_identity_auth_service_account)
    del user.identity.service_account.client_id
    del user.identity.service_account.username
    with application.copy_using(auth_type=AuthType.IDENTITY, user=user, verify_ssl=False) as app:
        yield app.host_inventory


@pytest.fixture()
def host_inventory_service_account_without_service_account(
    hbi_identity_auth_service_account: DynaBox, application: Application
) -> Generator[ApplicationHostInventory, None, None]:
    user = deepcopy(hbi_identity_auth_service_account)
    del user.identity.service_account
    with application.copy_using(auth_type=AuthType.IDENTITY, user=user, verify_ssl=False) as app:
        yield app.host_inventory


# Correct System identity is not tested here, because it has a different functionality
# See identity_cert_auth tests
parametrize_host_inventory_correct = pytest.mark.parametrize(
    "host_inventory_correct",
    # lazy_fixture(
    #     ["host_inventory_user_correct", "host_inventory_identity_auth_service_account"]
    # ),  TODO: https://issues.redhat.com/browse/IQE-2703
    [lf("host_inventory_user_correct")],
)


parametrize_host_inventory_invalid = pytest.mark.parametrize(
    "host_inventory_invalid, error_msg",
    [
        pytest.param(
            lf("host_inventory_blank_org_id"),
            "Identity Error: {'org_id': ['Length must be between 1 and 36.']}",
            id="blank_org_id",
        ),
        pytest.param(
            lf("host_inventory_without_org_id"),
            "Identity Error: {'org_id': ['Missing data for required field.']}",
            id="without_org_id",
        ),
        pytest.param(
            lf("host_inventory_invalid_type"),
            "Identity Error: {'type': ['Must be one of: IdentityType.SYSTEM, IdentityType.USER, "
            "IdentityType.SERVICE_ACCOUNT, IdentityType.ASSOCIATE, IdentityType.X509.']}",
            id="invalid_type",
        ),
        pytest.param(
            lf("host_inventory_blank_type"),
            "Identity Error: {'type': ['Must be one of: IdentityType.SYSTEM, IdentityType.USER, "
            "IdentityType.SERVICE_ACCOUNT, IdentityType.ASSOCIATE, IdentityType.X509.']}",
            id="blank_type",
        ),
        pytest.param(
            lf("host_inventory_without_type"),
            "Identity Error: {'type': ['Missing data for required field.']}",
            id="without_type",
        ),
        pytest.param(
            lf("host_inventory_invalid_auth_type"),
            "Identity Error: {'auth_type': ['Must be one of: AuthType.BASIC, AuthType.CERT, "
            "AuthType.JWT, AuthType.UHC, AuthType.SAML, AuthType.X509.']}",
            id="invalid_auth_type",
        ),
        pytest.param(
            lf("host_inventory_blank_auth_type"),
            "Identity Error: {'auth_type': ['Must be one of: AuthType.BASIC, AuthType.CERT, "
            "AuthType.JWT, AuthType.UHC, AuthType.SAML, AuthType.X509.']}",
            id="blank_auth_type",
        ),
        pytest.param(
            lf("host_inventory_without_auth_type"),
            "Identity Error: {'auth_type': ['Missing data for required field.']}",
            id="without_auth_type",
        ),
        pytest.param(
            lf("host_inventory_system_blank_cn"),
            "Identity Error: {'cn': ['Shorter than minimum length 1.']}",
            id="system_blank_cn",
        ),
        pytest.param(
            lf("host_inventory_system_without_cn"),
            "Identity Error: {'cn': ['Missing data for required field.']}",
            id="system_without_cn",
        ),
        pytest.param(
            lf("host_inventory_system_invalid_cert_type"),
            "Identity Error: {'cert_type': ['Must be one of: CertType.HYPERVISOR, CertType.RHUI, "
            "CertType.SAM, CertType.SATELLITE, CertType.SYSTEM.']}",
            id="system_invalid_cert_type",
        ),
        pytest.param(
            lf("host_inventory_system_blank_cert_type"),
            "Identity Error: {'cert_type': ['Must be one of: CertType.HYPERVISOR, CertType.RHUI, "
            "CertType.SAM, CertType.SATELLITE, CertType.SYSTEM.']}",
            id="system_blank_cert_type",
        ),
        pytest.param(
            lf("host_inventory_system_without_cert_type"),
            "Identity Error: {'cert_type': ['Missing data for required field.']}",
            id="system_without_cert_type",
        ),
        pytest.param(
            lf("host_inventory_system_blank_system"),
            [
                "Identity Error: {",
                "'cert_type': ['Missing data for required field.']",
                "'cn': ['Missing data for required field.']",
            ],
            id="system_blank_system",
        ),
        pytest.param(
            lf("host_inventory_system_without_system"),
            "Identity Error: {'system': ['Missing data for required field.']}",
            id="system_without_system",
        ),
        pytest.param(
            lf("host_inventory_service_account_blank_client_id"),
            "Identity Error: {'client_id': ['Shorter than minimum length 1.']}",
            id="service_account_blank_client_id",
        ),
        pytest.param(
            lf("host_inventory_service_account_without_client_id"),
            "Identity Error: {'client_id': ['Missing data for required field.']}",
            id="service_account_without_client_id",
        ),
        pytest.param(
            lf("host_inventory_service_account_blank_username"),
            "Identity Error: {'username': ['Shorter than minimum length 1.']}",
            id="service_account_blank_username",
        ),
        pytest.param(
            lf("host_inventory_service_account_without_username"),
            "Identity Error: {'username': ['Missing data for required field.']}",
            id="service_account_without_username",
        ),
        pytest.param(
            lf("host_inventory_service_account_blank_service_account"),
            [
                "Identity Error: {",
                "'client_id': ['Missing data for required field.']",
                "'username': ['Missing data for required field.']",
            ],
            id="service_account_blank_service_account",
        ),
        pytest.param(
            lf("host_inventory_service_account_without_service_account"),
            "Identity Error: {'service_account': ['Missing data for required field.']}",
            id="service_account_without_service_account",
        ),
    ],
)


@parametrize_host_inventory_invalid
@pytest.mark.ephemeral
def test_identity_invalid_get_hosts(
    host_inventory_invalid: ApplicationHostInventory, error_msg: str
):
    """
    Test that inventory doesn't accept requests with invalid identity header and it throws
    error with meaningful message.

    JIRA: https://issues.redhat.com/browse/RHCLOUD-11738

    metadata:
        requirements: inv-api-identity-validation
        assignee: fstavela
        importance: high
        negative: true
        title: Test invalid identity header - GET /hosts
    """
    with pytest.raises(ApiException) as err:
        host_inventory_invalid.apis.hosts.get_hosts_response()

    assert err.value.status == 401
    response = json.loads(err.value.body)

    # TODO: Uncomment when https://issues.redhat.com/browse/RHINENG-11389 is fixed
    # if isinstance(error_msg, list):
    #     assert all(msg in response["detail"] for msg in error_msg)
    # else:
    #     assert response["detail"] == error_msg
    assert response["detail"] == "Invalid token"


@parametrize_host_inventory_invalid
@pytest.mark.ephemeral
def test_identity_invalid_create_group(
    host_inventory_invalid: ApplicationHostInventory, error_msg: str
):
    """
    Test that inventory doesn't accept requests with invalid identity header and it throws
    error with meaningful message.

    JIRA: https://issues.redhat.com/browse/RHINENG-5819

    metadata:
        requirements: inv-api-identity-validation
        assignee: fstavela
        importance: high
        negative: true
        title: Test invalid identity header - POST /groups
    """
    with pytest.raises(ApiException) as err:
        host_inventory_invalid.apis.groups.create_group(generate_uuid(), wait_for_created=False)

    assert err.value.status == 401
    response = json.loads(err.value.body)

    # TODO: Uncomment when https://issues.redhat.com/browse/RHINENG-11389 is fixed
    # if isinstance(error_msg, list):
    #     assert all(msg in response["detail"] for msg in error_msg)
    # else:
    #     assert response["detail"] == error_msg
    assert response["detail"] == "Invalid token"


@parametrize_host_inventory_correct
@pytest.mark.ephemeral
def test_identity_correct_get_hosts(
    host_inventory: ApplicationHostInventory, host_inventory_correct: ApplicationHostInventory
):
    """
    Test that inventory accepts requests with correct identity header

    JIRA: https://issues.redhat.com/browse/RHINENG-5819

    metadata:
        requirements: inv-api-identity-validation
        assignee: fstavela
        importance: high
        title: Test correct identity header - GET /hosts
    """
    host_inventory.kafka.create_host()
    hosts = host_inventory_correct.apis.hosts.get_hosts()
    assert len(hosts)


@pytest.mark.ephemeral
def test_identity_correct_user_create_group(
    host_inventory_user_correct: ApplicationHostInventory,
    hbi_default_org_id: str,
    hbi_default_account_number: str,
    request: pytest.FixtureRequest,
):
    """
    Test that inventory accepts requests with correct identity header

    https://issues.redhat.com/browse/RHINENG-5819
    https://issues.redhat.com/browse/RHINENG-21925

    metadata:
        requirements: inv-api-identity-validation
        assignee: fstavela
        importance: high
        title: Test correct user identity header - POST /groups
    """
    group = host_inventory_user_correct.apis.groups.create_group(generate_uuid())

    @request.addfinalizer
    def cleanup():
        host_inventory_user_correct.apis.groups.delete_groups(group)

    assert group.org_id == hbi_default_org_id
    assert group.account == hbi_default_account_number


@pytest.mark.ephemeral
@pytest.mark.service_account
def test_identity_correct_service_account_create_group(
    host_inventory_identity_auth_service_account: ApplicationHostInventory,
    hbi_default_org_id: str,
    request: pytest.FixtureRequest,
):
    """
    Test that inventory accepts requests with correct identity header

    JIRA: https://issues.redhat.com/browse/RHINENG-5819

    metadata:
        requirements: inv-api-identity-validation
        assignee: fstavela
        importance: high
        title: Test correct service account identity header - POST /groups
    """
    group = host_inventory_identity_auth_service_account.apis.groups.create_group(generate_uuid())

    @request.addfinalizer
    def cleanup():
        host_inventory_identity_auth_service_account.apis.groups.delete_groups(group)

    assert group.org_id == hbi_default_org_id
    assert group.account is None

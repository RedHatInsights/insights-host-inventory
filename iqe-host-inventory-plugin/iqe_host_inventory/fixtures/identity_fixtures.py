from collections.abc import Generator
from copy import deepcopy
from typing import Any
from typing import Literal

import pytest
from dynaconf.utils.boxing import DynaBox
from iqe.base.application import Application
from iqe.base.auth import AuthType

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.fixtures.user_fixtures import get_user
from iqe_host_inventory.fixtures.user_fixtures import require_user
from iqe_host_inventory.tests.rest.test_tag import gen_tag
from iqe_host_inventory.utils.api_utils import criterion_hosts_in
from iqe_host_inventory.utils.api_utils import get_hosts
from iqe_host_inventory.utils.datagen_utils import generate_uuid
from iqe_host_inventory_api import HostsApi

# MQ Identity


def minimal_system_identity(
    cert_type: Literal["system", "satellite", "sam", "rhui", "hypervisor"],
):
    return {
        "identity": {
            "org_id": "123456",
            "type": "System",
            "auth_type": "cert-auth",
            "system": {"cn": "ca01d910-4d00-4080-aff4-ae17a8c46547", "cert_type": cert_type},
        }
    }


MINIMAL_USER_IDENTITY = {
    "identity": {
        "org_id": "123456",
        "type": "User",
        "auth_type": "basic-auth",
    }
}


MINIMAL_SERVICE_ACCOUNT_IDENTITY = {
    "identity": {
        "org_id": "123456",
        "type": "ServiceAccount",
        "auth_type": "jwt-auth",
        "service_account": {
            "client_id": "b69eaf9e-e6a6-4f9e-805e-02987daddfbd",
            "username": "iqe-hbi-service-account",
        },
    }
}


@pytest.fixture(params=["system", "satellite", "sam", "rhui", "hypervisor"])
def get_system_identity(request) -> dict[str, Any]:
    return minimal_system_identity(request.param)


def get_user_identity() -> dict[str, Any]:
    identity = deepcopy(MINIMAL_USER_IDENTITY)
    return identity


def get_service_account_identity() -> dict[str, Any]:
    identity = deepcopy(MINIMAL_SERVICE_ACCOUNT_IDENTITY)
    return identity


@pytest.fixture(params=["user", "service_account"])
def get_non_system_identity(request) -> dict[str, Any]:
    if request.param == "user":
        return get_user_identity()
    return get_service_account_identity()


@pytest.fixture()
def system_identity_correct(
    hbi_default_org_id: str, get_system_identity: dict[str, Any]
) -> dict[str, Any]:
    identity = get_system_identity
    identity["identity"]["org_id"] = hbi_default_org_id
    return identity


@pytest.fixture()
def user_identity_correct(hbi_default_org_id: str) -> dict[str, Any]:
    identity = get_user_identity()
    identity["identity"]["org_id"] = hbi_default_org_id
    return identity


@pytest.fixture()
def service_account_identity_correct(hbi_default_org_id: str) -> dict[str, Any]:
    identity = get_service_account_identity()
    identity["identity"]["org_id"] = hbi_default_org_id
    return identity


@pytest.fixture()
def non_system_identity_correct(
    hbi_default_org_id: str, get_non_system_identity: dict[str, Any]
) -> dict[str, Any]:
    identity = get_non_system_identity
    identity["identity"]["org_id"] = hbi_default_org_id
    return identity


# REST Identity


@pytest.fixture(scope="session")
def hbi_maybe_identity_auth_user(application: Application) -> DynaBox | None:
    return get_user(application, "identity_auth_user")


@pytest.fixture(scope="session")
def hbi_identity_auth_user(application: Application) -> DynaBox:
    return require_user(application, "identity_auth_user")


@pytest.fixture(scope="session")
def hbi_maybe_application_identity_auth_user(
    application: Application, hbi_maybe_identity_auth_user: DynaBox | None
) -> Generator[Application | None, None, None]:
    if hbi_maybe_identity_auth_user is None:
        yield None
        return

    with application.copy_using(
        auth_type=AuthType.IDENTITY, user=hbi_maybe_identity_auth_user, verify_ssl=False
    ) as app:
        yield app


@pytest.fixture(scope="session")
def hbi_maybe_identity_auth_system(application: Application) -> DynaBox | None:
    return get_user(application, "identity_auth_system")


@pytest.fixture(scope="session")
def hbi_identity_auth_system(application: Application) -> DynaBox:
    return require_user(application, "identity_auth_system")


@pytest.fixture(scope="session")
def hbi_maybe_application_identity_auth_system(
    application: Application, hbi_maybe_identity_auth_system: DynaBox | None
) -> Generator[Application | None, None, None]:
    if hbi_maybe_identity_auth_system is None:
        yield None
        return

    with application.copy_using(
        auth_type=AuthType.IDENTITY, user=hbi_maybe_identity_auth_system, verify_ssl=False
    ) as app:
        yield app


@pytest.fixture(scope="session")
def hbi_maybe_identity_auth_service_account(application: Application) -> DynaBox | None:
    return get_user(application, "identity_auth_service_account")


@pytest.fixture(scope="session")
def hbi_identity_auth_service_account(application: Application) -> DynaBox:
    return require_user(application, "identity_auth_service_account")


@pytest.fixture(scope="session")
def hbi_maybe_application_identity_auth_service_account(
    application: Application, hbi_maybe_identity_auth_service_account: DynaBox | None
) -> Generator[Application | None, None, None]:
    if hbi_maybe_identity_auth_service_account is None:
        yield None
        return

    with application.copy_using(
        auth_type=AuthType.IDENTITY, user=hbi_maybe_identity_auth_service_account, verify_ssl=False
    ) as app:
        yield app


@pytest.fixture(scope="session")
def hbi_identity_auth_x509_rhsm(application: Application) -> DynaBox:
    return require_user(application, "identity_auth_x509_rhsm")


@pytest.fixture(scope="session")
def inventory_cert_system_owner_id(hbi_identity_auth_system: DynaBox) -> str:
    return hbi_identity_auth_system.identity.system.cn


@pytest.fixture(params=["system", "satellite", "sam", "rhui", "hypervisor"])
def host_inventory_system_correct(
    request, application: Application, hbi_identity_auth_system: DynaBox
) -> Generator[ApplicationHostInventory, None, None]:
    user = deepcopy(hbi_identity_auth_system)
    user.identity.system.cert_type = request.param
    with application.copy_using(auth_type=AuthType.IDENTITY, user=user, verify_ssl=False) as app:
        yield app.host_inventory


# Setup fixtures


@pytest.fixture
def hbi_setup_tagged_hosts_for_identity_cert_auth(
    host_inventory: ApplicationHostInventory,
    inventory_cert_system_owner_id: str,
    openapi_client: HostsApi,
):
    without_owner_id_tag = gen_tag()
    correct_owner_id_tag = gen_tag()
    wrong_owner_id_tag = gen_tag()
    host_data = host_inventory.datagen.create_host_data()
    host_data["tags"] = [without_owner_id_tag]
    host_data_correct = dict(
        host_inventory.datagen.create_host_data(), tags=[correct_owner_id_tag]
    )
    host_data_correct["system_profile"]["owner_id"] = inventory_cert_system_owner_id
    host_data_wrong = dict(host_inventory.datagen.create_host_data(), tags=[wrong_owner_id_tag])
    host_data_wrong["system_profile"]["owner_id"] = generate_uuid()
    host = host_inventory.kafka.create_host(host_data_correct)
    host_without_owner_id = host_inventory.kafka.create_host(host_data)
    host_with_different_owner_id = host_inventory.kafka.create_host(host_data_wrong)
    get_hosts(
        openapi_client,
        criteria=[
            (
                criterion_hosts_in,
                [host.id, host_without_owner_id.id, host_with_different_owner_id.id],
            )
        ],
    )
    return {
        "without_owner_id_tag": without_owner_id_tag,
        "correct_owner_id_tag": correct_owner_id_tag,
        "wrong_owner_id_tag": wrong_owner_id_tag,
        "without_owner_id_host": host_without_owner_id,
        "correct_owner_id_host": host,
        "wrong_owner_id_host": host_with_different_owner_id,
    }

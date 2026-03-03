import pytest
from dynaconf.utils.boxing import DynaBox
from iqe.base.application import Application

from iqe_host_inventory import ApplicationHostInventory

pytest_plugins = [
    "iqe_host_inventory.fixtures.api_fixtures",
    "iqe_host_inventory.fixtures.db_fixtures",
    "iqe_host_inventory.fixtures.exports_fixtures",
    "iqe_host_inventory.fixtures.filter_fixtures",
    "iqe_host_inventory.fixtures.groups_fixtures",
    "iqe_host_inventory.fixtures.cleanup_fixtures",
    "iqe_host_inventory.fixtures.identity_fixtures",
    "iqe_host_inventory.fixtures.kafka_fixtures",
    "iqe_host_inventory.fixtures.kessel_fixtures",
    "iqe_host_inventory.fixtures.rbac_fixtures",
    "iqe_host_inventory.fixtures.staleness_fixtures",
    "iqe_host_inventory.fixtures.upload_fixtures",
    "iqe_host_inventory.fixtures.user_fixtures",
    "iqe_host_inventory.fixtures.feature_flag_fixtures",
]


def pytest_configure(config):
    config.addinivalue_line("markers", "backend: All tests related to backend")
    config.addinivalue_line(
        "markers",
        "concurrency: Tests that involve making multiple concurrent requests "
        "against a given endpoint",
    )
    config.addinivalue_line(
        "markers",
        "multi_account: Tests that require two different application user accounts to execute",
    )
    config.addinivalue_line("markers", "reaper_script: Tests that need to run HBI reaper script")
    config.addinivalue_line(
        "markers",
        "resilience: Tests intended to verify the graceful shutdown of the HBI services",
    )
    config.addinivalue_line(
        "markers", "cert_auth: Tests that require certificates for authorization"
    )
    config.addinivalue_line("markers", "rbac_dependent: Tests that require RBAC to be running")


@pytest.fixture(scope="session")
def host_inventory(application: Application) -> ApplicationHostInventory:
    return application.host_inventory


@pytest.fixture(scope="session")
def host_inventory_cert_auth(
    hbi_application_cert_auth: Application,
) -> ApplicationHostInventory:
    return hbi_application_cert_auth.host_inventory


@pytest.fixture(scope="session")
def host_inventory_non_org_admin(
    hbi_maybe_application_non_org_admin: Application | None,
) -> ApplicationHostInventory:
    if hbi_maybe_application_non_org_admin is None:
        pytest.fail("'non org admin' user is not properly defined in the config")
    return hbi_maybe_application_non_org_admin.host_inventory


@pytest.fixture(scope="session")
def host_inventory_non_org_admin_cert_auth(
    hbi_maybe_application_non_org_admin_cert_auth: Application | None,
) -> ApplicationHostInventory:
    if hbi_maybe_application_non_org_admin_cert_auth is None:
        pytest.fail("'non org admin' user is not properly defined in the config")
    return hbi_maybe_application_non_org_admin_cert_auth.host_inventory


@pytest.fixture(scope="session")
def host_inventory_secondary(hbi_application_secondary: Application) -> ApplicationHostInventory:
    return hbi_application_secondary.host_inventory


@pytest.fixture(scope="session")
def host_inventory_sa_1(
    hbi_maybe_application_service_account_1: Application | None,
) -> ApplicationHostInventory:
    if hbi_maybe_application_service_account_1 is None:
        pytest.fail("'service account 1' is not properly defined in the config")
    return hbi_maybe_application_service_account_1.host_inventory


@pytest.fixture(scope="session")
def host_inventory_sa_2(
    hbi_maybe_application_service_account_2: Application | None,
) -> ApplicationHostInventory:
    if hbi_maybe_application_service_account_2 is None:
        pytest.fail("'service account 2' is not properly defined in the config")
    return hbi_maybe_application_service_account_2.host_inventory


@pytest.fixture(scope="session")
def host_inventory_identity_auth_user(
    hbi_maybe_application_identity_auth_user: Application | None,
) -> ApplicationHostInventory:
    if hbi_maybe_application_identity_auth_user is None:
        pytest.fail("'identity auth user' is not properly defined in the config")
    return hbi_maybe_application_identity_auth_user.host_inventory


@pytest.fixture(scope="session")
def host_inventory_identity_auth_system(
    hbi_maybe_application_identity_auth_system: DynaBox | None,
) -> ApplicationHostInventory:
    if hbi_maybe_application_identity_auth_system is None:
        pytest.fail("'identity auth system' is not properly defined in the config")
    return hbi_maybe_application_identity_auth_system.host_inventory


@pytest.fixture(scope="session")
def host_inventory_identity_auth_service_account(
    hbi_maybe_application_identity_auth_service_account: DynaBox | None,
) -> ApplicationHostInventory:
    if hbi_maybe_application_identity_auth_service_account is None:
        pytest.fail("'identity auth service account' is not properly defined in the config")
    return hbi_maybe_application_identity_auth_service_account.host_inventory

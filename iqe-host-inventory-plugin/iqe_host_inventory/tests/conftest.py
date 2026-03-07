# mypy: disallow-untyped-defs

import http.client
import logging
from collections.abc import Generator
from copy import deepcopy
from os import getenv
from random import sample

import pytest
from _pytest.config import Config
from _pytest.config.argparsing import Parser
from _pytest.fixtures import FixtureRequest
from _pytest.nodes import Item
from dynaconf.utils.boxing import DynaBox
from iqe.base.application import Application
from iqe.users.user_provider import UserProvider

from iqe_host_inventory import ApplicationHostInventory
from iqe_host_inventory.fixtures.cleanup_fixtures import HBICleanupRegistry
from iqe_host_inventory.fixtures.feature_flag_fixtures import _ensure_ungrouped_group_exists
from iqe_host_inventory.modeling.uploads import HostData
from iqe_host_inventory.modeling.wrappers import HostWrapper
from iqe_host_inventory.utils import get_username
from iqe_host_inventory.utils.datagen_utils import generate_uuid

logger = logging.getLogger(__name__)


def pytest_addoption(parser: Parser) -> None:
    parser.addoption(
        "--skip-data-setup",
        action="store_true",
        default=False,
        help="Skip setting up data on secondary account in ephemeral environments",
    )
    parser.addoption(
        "--kessel",
        action="store_true",
        default=False,
        help="Enable Kessel feature flags and tests",
    )
    parser.addoption(
        "--http-debug",
        action="store_true",
        default=False,
        help="Enable verbose HTTP debug logging for urllib3 and http.client",
    )


def pytest_collection_modifyitems(config: Config, items: list[Item]) -> None:
    if getenv("ENV_FOR_DYNACONF", "stage_proxy").lower() != "clowder_smoke" or config.getoption(
        "--kessel"
    ):
        # Don't skip Kessel tests in Stage and Prod, or if --kessel option is used
        return

    skip_kessel = pytest.mark.skip(
        reason="Skipping Kessel tests in ephemeral env if --kessel option is not used"
    )
    SKIPPED_MODULES = (
        "test_kessel_groups.py",
        "test_kessel_host_replication.py",
        "test_kessel_rbac_granular.py",
        "test_kessel_ungrouped.py",
    )
    for item in items:
        if item.parent is not None and item.parent.name in SKIPPED_MODULES:
            item.add_marker(skip_kessel)


@pytest.fixture(scope="session", autouse=True)
def enable_http_debug_logging(request: FixtureRequest) -> Generator[None, None, None]:
    """Enable verbose HTTP logging for debugging connection issues like RemoteDisconnected.

    Usage: pytest --http-debug -s

    This enables DEBUG logging for:
    - urllib3: Connection pooling, request/response cycles, retries, connection reuse
    - http.client: Low-level HTTP wire protocol (raw requests/responses)
    - iqe_host_inventory_api.rest: Response body logging
    - iqe_host_inventory_api_v7.rest: Response body logging (v7 API client)
    """
    if not request.config.getoption("--http-debug", default=False):
        yield
        return

    # Create a dedicated handler for HTTP debug output
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)

    # Enable urllib3 debug logging
    urllib3_logger = logging.getLogger("urllib3")
    urllib3_logger.setLevel(logging.DEBUG)
    urllib3_logger.addHandler(handler)

    # Enable the IQE API client REST module logging (both v1 and v7)
    rest_logger = logging.getLogger("iqe_host_inventory_api.rest")
    rest_logger.setLevel(logging.DEBUG)
    rest_logger.addHandler(handler)

    rest_v7_logger = logging.getLogger("iqe_host_inventory_api_v7.rest")
    rest_v7_logger.setLevel(logging.DEBUG)
    rest_v7_logger.addHandler(handler)

    # Enable http.client debug logging (prints directly to stdout)
    # This shows the raw HTTP wire protocol
    original_debuglevel = http.client.HTTPConnection.debuglevel
    http.client.HTTPConnection.debuglevel = 1

    logger.info("HTTP debug logging enabled for urllib3, http.client, and IQE REST clients")

    yield

    # Cleanup
    urllib3_logger.removeHandler(handler)
    rest_logger.removeHandler(handler)
    rest_v7_logger.removeHandler(handler)
    http.client.HTTPConnection.debuglevel = original_debuglevel

    logger.info("HTTP debug logging disabled")


@pytest.fixture(scope="session", autouse=True)
def configure_robust_http_retries() -> Generator[None, None, None]:
    """Configure urllib3 with robust retry settings for connection errors.

    This helps mitigate RemoteDisconnected and SSLEOFError issues that occur
    when the server/load balancer closes idle keep-alive connections.

    The retry configuration:
    - total=5: Maximum 5 retry attempts
    - connect=3: Retry up to 3 times on connection errors
    - read=3: Retry up to 3 times on read errors
    - backoff_factor=0.5: Exponential backoff (0.5s, 1s, 2s, ...)
    - raise_on_status=False: Don't raise on HTTP error status codes (let the app handle them)
    """
    import urllib3.util.retry

    # Store original default retry
    original_retry = urllib3.util.retry.Retry.DEFAULT

    # Configure robust retries for connection issues
    robust_retry = urllib3.util.retry.Retry(
        total=5,
        connect=3,
        read=3,
        backoff_factor=0.5,
        raise_on_status=False,
        # Retry on these HTTP methods (all methods that could have connection issues)
        allowed_methods=frozenset(["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]),
    )

    # Set as the new default
    urllib3.util.retry.Retry.DEFAULT = robust_retry

    logger.info("Configured robust HTTP retries: total=5, connect=3, read=3, backoff_factor=0.5")

    yield

    # Restore original default
    urllib3.util.retry.Retry.DEFAULT = original_retry


@pytest.fixture(scope="session", autouse=True)
def _flush_kafka(host_inventory: ApplicationHostInventory) -> Generator[None, None, None]:
    "temporary hack - dishka based cleans up itself"

    yield
    kafka = host_inventory.kafka
    # only do the cleanup if the producer was actually in use
    # this prevents setup errors in teardown
    if "_producer" in kafka.__dict__:
        kafka._producer.flush(timeout=15)


@pytest.fixture(scope="session", autouse=True)
def enable_kessel_backend_flags(
    request: FixtureRequest,
    host_inventory: ApplicationHostInventory,
) -> None:
    if request.config.getoption("--kessel"):
        host_inventory.unleash.toggle_feature_flag(
            host_inventory.unleash.kessel_phase_1_flag, enable=True
        )
        host_inventory.unleash.toggle_feature_flag(
            host_inventory.unleash.kessel_groups_flag, enable=False
        )
        _ensure_ungrouped_group_exists(host_inventory)


# CLEANUP

# DEFAULT USER


@pytest.fixture(scope="session", autouse=True)
def hbi_cleanup_default_user_session(
    host_inventory: ApplicationHostInventory, hbi_cleanup_session: HBICleanupRegistry
) -> None:
    """
    Deletes all resources created by default user which are registered for cleanup
    at the end of the test session
    """
    hbi_cleanup_session(host_inventory)


@pytest.fixture(scope="package", autouse=True)
def hbi_cleanup_default_user_package(
    host_inventory: ApplicationHostInventory, hbi_cleanup_package: HBICleanupRegistry
) -> None:
    """
    Deletes all resources created by default user which are registered for cleanup
    at the end of the test package
    """
    hbi_cleanup_package(host_inventory)


@pytest.fixture(scope="module", autouse=True)
def hbi_cleanup_default_user_module(
    host_inventory: ApplicationHostInventory, hbi_cleanup_module: HBICleanupRegistry
) -> None:
    """
    Deletes all resources created by default user which are registered for cleanup
    at the end of the test module
    """
    hbi_cleanup_module(host_inventory)


@pytest.fixture(scope="class", autouse=True)
def hbi_cleanup_default_user_class(
    host_inventory: ApplicationHostInventory, hbi_cleanup_class: HBICleanupRegistry
) -> None:
    """
    Deletes all resources created by default user which are registered for cleanup
    at the end of the test class
    """
    hbi_cleanup_class(host_inventory)


@pytest.fixture(scope="function", autouse=True)
def hbi_cleanup_default_user_function(
    host_inventory: ApplicationHostInventory, hbi_cleanup_function: HBICleanupRegistry
) -> None:
    """
    Deletes all resources created by default user which are registered for cleanup
    at the end of the test function
    """
    hbi_cleanup_function(host_inventory)


# DEFAULT USER CERT AUTH


@pytest.fixture(scope="session", autouse=True)
def hbi_cleanup_cert_auth_session(
    host_inventory_cert_auth: ApplicationHostInventory,
    hbi_cleanup_session: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by default user cert auth which are registered for cleanup
    at the end of the test session
    """
    hbi_cleanup_session(host_inventory_cert_auth)


@pytest.fixture(scope="package", autouse=True)
def hbi_cleanup_cert_auth_package(
    host_inventory_cert_auth: ApplicationHostInventory,
    hbi_cleanup_package: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by default user cert auth which are registered for cleanup
    at the end of the test package
    """
    hbi_cleanup_package(host_inventory_cert_auth)


@pytest.fixture(scope="module", autouse=True)
def hbi_cleanup_cert_auth_module(
    host_inventory_cert_auth: ApplicationHostInventory,
    hbi_cleanup_module: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by default user cert auth which are registered for cleanup
    at the end of the test module
    """
    hbi_cleanup_module(host_inventory_cert_auth)


@pytest.fixture(scope="class", autouse=True)
def hbi_cleanup_cert_auth_class(
    host_inventory_cert_auth: ApplicationHostInventory,
    hbi_cleanup_class: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by default user cert auth which are registered for cleanup
    at the end of the test class
    """
    hbi_cleanup_class(host_inventory_cert_auth)


@pytest.fixture(scope="function", autouse=True)
def hbi_cleanup_cert_auth_function(
    host_inventory_cert_auth: ApplicationHostInventory,
    hbi_cleanup_function: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by default user cert auth which are registered for cleanup
    at the end of the test function
    """
    hbi_cleanup_function(host_inventory_cert_auth)


# NON ORG ADMIN USER


@pytest.fixture(scope="session", autouse=True)
def hbi_cleanup_non_org_admin_user_session(
    hbi_maybe_application_non_org_admin: Application | None,
    hbi_cleanup_session: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by non org admin user which are registered for cleanup
    at the end of the test session
    """
    if hbi_maybe_application_non_org_admin is not None:
        hbi_cleanup_session(hbi_maybe_application_non_org_admin.host_inventory)


@pytest.fixture(scope="package", autouse=True)
def hbi_cleanup_non_org_admin_user_package(
    hbi_maybe_application_non_org_admin: Application | None,
    hbi_cleanup_package: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by non org admin user which are registered for cleanup
    at the end of the test package
    """
    if hbi_maybe_application_non_org_admin is not None:
        hbi_cleanup_package(hbi_maybe_application_non_org_admin.host_inventory)


@pytest.fixture(scope="module", autouse=True)
def hbi_cleanup_non_org_admin_user_module(
    hbi_maybe_application_non_org_admin: Application | None,
    hbi_cleanup_module: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by non org admin user which are registered for cleanup
    at the end of the test module
    """
    if hbi_maybe_application_non_org_admin is not None:
        hbi_cleanup_module(hbi_maybe_application_non_org_admin.host_inventory)


@pytest.fixture(scope="class", autouse=True)
def hbi_cleanup_non_org_admin_user_class(
    hbi_maybe_application_non_org_admin: Application | None,
    hbi_cleanup_class: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by non org admin user which are registered for cleanup
    at the end of the test class
    """
    if hbi_maybe_application_non_org_admin is not None:
        hbi_cleanup_class(hbi_maybe_application_non_org_admin.host_inventory)


@pytest.fixture(scope="function", autouse=True)
def hbi_cleanup_non_org_admin_user_function(
    hbi_maybe_application_non_org_admin: Application | None,
    hbi_cleanup_function: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by non org admin user which are registered for cleanup
    at the end of the test function
    """
    if hbi_maybe_application_non_org_admin is not None:
        hbi_cleanup_function(hbi_maybe_application_non_org_admin.host_inventory)


# NON ORG ADMIN USER CERT AUTH


@pytest.fixture(scope="session", autouse=True)
def hbi_cleanup_non_org_admin_cert_auth_session(
    hbi_maybe_application_non_org_admin_cert_auth: Application | None,
    hbi_cleanup_session: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by non org admin user cert auth which are registered for cleanup
    at the end of the test session
    """
    if hbi_maybe_application_non_org_admin_cert_auth is not None:
        hbi_cleanup_session(hbi_maybe_application_non_org_admin_cert_auth.host_inventory)


@pytest.fixture(scope="package", autouse=True)
def hbi_cleanup_non_org_admin_cert_auth_package(
    hbi_maybe_application_non_org_admin_cert_auth: Application | None,
    hbi_cleanup_package: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by non org admin user cert auth which are registered for cleanup
    at the end of the test package
    """
    if hbi_maybe_application_non_org_admin_cert_auth is not None:
        hbi_cleanup_package(hbi_maybe_application_non_org_admin_cert_auth.host_inventory)


@pytest.fixture(scope="module", autouse=True)
def hbi_cleanup_non_org_admin_cert_auth_module(
    hbi_maybe_application_non_org_admin_cert_auth: Application | None,
    hbi_cleanup_module: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by non org admin user cert auth which are registered for cleanup
    at the end of the test module
    """
    if hbi_maybe_application_non_org_admin_cert_auth is not None:
        hbi_cleanup_module(hbi_maybe_application_non_org_admin_cert_auth.host_inventory)


@pytest.fixture(scope="class", autouse=True)
def hbi_cleanup_non_org_admin_cert_auth_class(
    hbi_maybe_application_non_org_admin_cert_auth: Application | None,
    hbi_cleanup_class: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by non org admin user cert auth which are registered for cleanup
    at the end of the test class
    """
    if hbi_maybe_application_non_org_admin_cert_auth is not None:
        hbi_cleanup_class(hbi_maybe_application_non_org_admin_cert_auth.host_inventory)


@pytest.fixture(scope="function", autouse=True)
def hbi_cleanup_non_org_admin_cert_auth_function(
    hbi_maybe_application_non_org_admin_cert_auth: Application | None,
    hbi_cleanup_function: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by non org admin user cert auth which are registered for cleanup
    at the end of the test function
    """
    if hbi_maybe_application_non_org_admin_cert_auth is not None:
        hbi_cleanup_function(hbi_maybe_application_non_org_admin_cert_auth.host_inventory)


# SECONDARY USER


@pytest.fixture(scope="session", autouse=True)
def hbi_cleanup_secondary_user_session(
    hbi_maybe_application_secondary: Application | None,
    hbi_cleanup_session: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by secondary user which are registered for cleanup
    at the end of the test session
    """
    if hbi_maybe_application_secondary is not None:
        hbi_cleanup_session(hbi_maybe_application_secondary.host_inventory)


@pytest.fixture(scope="package", autouse=True)
def hbi_cleanup_secondary_user_package(
    hbi_maybe_application_secondary: Application | None,
    hbi_cleanup_package: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by secondary user which are registered for cleanup
    at the end of the test package
    """
    if hbi_maybe_application_secondary is not None:
        hbi_cleanup_package(hbi_maybe_application_secondary.host_inventory)


@pytest.fixture(scope="module", autouse=True)
def hbi_cleanup_secondary_user_module(
    hbi_maybe_application_secondary: Application | None,
    hbi_cleanup_module: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by secondary user which are registered for cleanup
    at the end of the test module
    """
    if hbi_maybe_application_secondary is not None:
        hbi_cleanup_module(hbi_maybe_application_secondary.host_inventory)


@pytest.fixture(scope="class", autouse=True)
def hbi_cleanup_secondary_user_class(
    hbi_maybe_application_secondary: Application | None,
    hbi_cleanup_class: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by secondary user which are registered for cleanup
    at the end of the test class
    """
    if hbi_maybe_application_secondary is not None:
        hbi_cleanup_class(hbi_maybe_application_secondary.host_inventory)


@pytest.fixture(scope="function", autouse=True)
def hbi_cleanup_secondary_user_function(
    hbi_maybe_application_secondary: Application | None,
    hbi_cleanup_function: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by secondary user which are registered for cleanup
    at the end of the test function
    """
    if hbi_maybe_application_secondary is not None:
        hbi_cleanup_function(hbi_maybe_application_secondary.host_inventory)


# FRONTEND USER


@pytest.fixture(scope="session", autouse=True)
def hbi_cleanup_frontend_user_session(
    hbi_maybe_application_frontend: Application | None,
    hbi_cleanup_session: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by frontend user which are registered for cleanup
    at the end of the test session
    """
    if hbi_maybe_application_frontend is not None:
        hbi_cleanup_session(hbi_maybe_application_frontend.host_inventory)


@pytest.fixture(scope="package", autouse=True)
def hbi_cleanup_frontend_user_package(
    hbi_maybe_application_frontend: Application | None,
    hbi_cleanup_package: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by frontend user which are registered for cleanup
    at the end of the test package
    """
    if hbi_maybe_application_frontend is not None:
        hbi_cleanup_package(hbi_maybe_application_frontend.host_inventory)


@pytest.fixture(scope="module", autouse=True)
def hbi_cleanup_frontend_user_module(
    hbi_maybe_application_frontend: Application | None,
    hbi_cleanup_module: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by frontend user which are registered for cleanup
    at the end of the test module
    """
    if hbi_maybe_application_frontend is not None:
        hbi_cleanup_module(hbi_maybe_application_frontend.host_inventory)


@pytest.fixture(scope="class", autouse=True)
def hbi_cleanup_frontend_user_class(
    hbi_maybe_application_frontend: Application | None,
    hbi_cleanup_class: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by frontend user which are registered for cleanup
    at the end of the test class
    """
    if hbi_maybe_application_frontend is not None:
        hbi_cleanup_class(hbi_maybe_application_frontend.host_inventory)


@pytest.fixture(scope="function", autouse=True)
def hbi_cleanup_frontend_user_function(
    hbi_maybe_application_frontend: Application | None,
    hbi_cleanup_function: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by frontend user which are registered for cleanup
    at the end of the test function
    """
    if hbi_maybe_application_frontend is not None:
        hbi_cleanup_function(hbi_maybe_application_frontend.host_inventory)


# SERVICE ACCOUNT 1


@pytest.fixture(scope="session", autouse=True)
def hbi_cleanup_service_account_1_session(
    hbi_maybe_application_service_account_1: Application | None,
    hbi_cleanup_session: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by service account 1 which are registered for cleanup
    at the end of the test session
    """
    if hbi_maybe_application_service_account_1 is not None:
        hbi_cleanup_session(hbi_maybe_application_service_account_1.host_inventory)


@pytest.fixture(scope="package", autouse=True)
def hbi_cleanup_service_account_1_package(
    hbi_maybe_application_service_account_1: Application | None,
    hbi_cleanup_package: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by service account 1 which are registered for cleanup
    at the end of the test package
    """
    if hbi_maybe_application_service_account_1 is not None:
        hbi_cleanup_package(hbi_maybe_application_service_account_1.host_inventory)


@pytest.fixture(scope="module", autouse=True)
def hbi_cleanup_service_account_1_module(
    hbi_maybe_application_service_account_1: Application | None,
    hbi_cleanup_module: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by service account 1 which are registered for cleanup
    at the end of the test module
    """
    if hbi_maybe_application_service_account_1 is not None:
        hbi_cleanup_module(hbi_maybe_application_service_account_1.host_inventory)


@pytest.fixture(scope="class", autouse=True)
def hbi_cleanup_service_account_1_class(
    hbi_maybe_application_service_account_1: Application | None,
    hbi_cleanup_class: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by service account 1 which are registered for cleanup
    at the end of the test class
    """
    if hbi_maybe_application_service_account_1 is not None:
        hbi_cleanup_class(hbi_maybe_application_service_account_1.host_inventory)


@pytest.fixture(scope="function", autouse=True)
def hbi_cleanup_service_account_1_function(
    hbi_maybe_application_service_account_1: Application | None,
    hbi_cleanup_function: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by service account 1 which are registered for cleanup
    at the end of the test function
    """
    if hbi_maybe_application_service_account_1 is not None:
        hbi_cleanup_function(hbi_maybe_application_service_account_1.host_inventory)


# SERVICE ACCOUNT 2


@pytest.fixture(scope="session", autouse=True)
def hbi_cleanup_service_account_2_session(
    hbi_maybe_application_service_account_2: Application | None,
    hbi_cleanup_session: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by service account 2 which are registered for cleanup
    at the end of the test session
    """
    if hbi_maybe_application_service_account_2 is not None:
        hbi_cleanup_session(hbi_maybe_application_service_account_2.host_inventory)


@pytest.fixture(scope="package", autouse=True)
def hbi_cleanup_service_account_2_package(
    hbi_maybe_application_service_account_2: Application | None,
    hbi_cleanup_package: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by service account 2 which are registered for cleanup
    at the end of the test package
    """
    if hbi_maybe_application_service_account_2 is not None:
        hbi_cleanup_package(hbi_maybe_application_service_account_2.host_inventory)


@pytest.fixture(scope="module", autouse=True)
def hbi_cleanup_service_account_2_module(
    hbi_maybe_application_service_account_2: Application | None,
    hbi_cleanup_module: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by service account 2 which are registered for cleanup
    at the end of the test module
    """
    if hbi_maybe_application_service_account_2 is not None:
        hbi_cleanup_module(hbi_maybe_application_service_account_2.host_inventory)


@pytest.fixture(scope="class", autouse=True)
def hbi_cleanup_service_account_2_class(
    hbi_maybe_application_service_account_2: Application | None,
    hbi_cleanup_class: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by service account 2 which are registered for cleanup
    at the end of the test class
    """
    if hbi_maybe_application_service_account_2 is not None:
        hbi_cleanup_class(hbi_maybe_application_service_account_2.host_inventory)


@pytest.fixture(scope="function", autouse=True)
def hbi_cleanup_service_account_2_function(
    hbi_maybe_application_service_account_2: Application | None,
    hbi_cleanup_function: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by service account 2 which are registered for cleanup
    at the end of the test function
    """
    if hbi_maybe_application_service_account_2 is not None:
        hbi_cleanup_function(hbi_maybe_application_service_account_2.host_inventory)


# IDENTITY AUTH USER


@pytest.fixture(scope="session", autouse=True)
def hbi_cleanup_identity_auth_user_session(
    hbi_maybe_application_identity_auth_user: Application | None,
    hbi_cleanup_session: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by identity auth user which are registered for cleanup
    at the end of the test session
    """
    if hbi_maybe_application_identity_auth_user is not None:
        hbi_cleanup_session(hbi_maybe_application_identity_auth_user.host_inventory)


@pytest.fixture(scope="package", autouse=True)
def hbi_cleanup_identity_auth_user_package(
    hbi_maybe_application_identity_auth_user: Application | None,
    hbi_cleanup_package: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by identity auth user which are registered for cleanup
    at the end of the test package
    """
    if hbi_maybe_application_identity_auth_user is not None:
        hbi_cleanup_package(hbi_maybe_application_identity_auth_user.host_inventory)


@pytest.fixture(scope="module", autouse=True)
def hbi_cleanup_identity_auth_user_module(
    hbi_maybe_application_identity_auth_user: Application | None,
    hbi_cleanup_module: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by identity auth user which are registered for cleanup
    at the end of the test module
    """
    if hbi_maybe_application_identity_auth_user is not None:
        hbi_cleanup_module(hbi_maybe_application_identity_auth_user.host_inventory)


@pytest.fixture(scope="class", autouse=True)
def hbi_cleanup_identity_auth_user_class(
    hbi_maybe_application_identity_auth_user: Application | None,
    hbi_cleanup_class: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by identity auth user which are registered for cleanup
    at the end of the test class
    """
    if hbi_maybe_application_identity_auth_user is not None:
        hbi_cleanup_class(hbi_maybe_application_identity_auth_user.host_inventory)


@pytest.fixture(scope="function", autouse=True)
def hbi_cleanup_identity_auth_user_function(
    hbi_maybe_application_identity_auth_user: Application | None,
    hbi_cleanup_function: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by identity auth user which are registered for cleanup
    at the end of the test function
    """
    if hbi_maybe_application_identity_auth_user is not None:
        hbi_cleanup_function(hbi_maybe_application_identity_auth_user.host_inventory)


# IDENTITY AUTH SYSTEM


@pytest.fixture(scope="session", autouse=True)
def hbi_cleanup_identity_auth_system_session(
    hbi_maybe_application_identity_auth_system: Application | None,
    hbi_cleanup_session: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by identity auth system which are registered for cleanup
    at the end of the test session
    """
    if hbi_maybe_application_identity_auth_system is not None:
        hbi_cleanup_session(hbi_maybe_application_identity_auth_system.host_inventory)


@pytest.fixture(scope="package", autouse=True)
def hbi_cleanup_identity_auth_system_package(
    hbi_maybe_application_identity_auth_system: Application | None,
    hbi_cleanup_package: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by identity auth system which are registered for cleanup
    at the end of the test package
    """
    if hbi_maybe_application_identity_auth_system is not None:
        hbi_cleanup_package(hbi_maybe_application_identity_auth_system.host_inventory)


@pytest.fixture(scope="module", autouse=True)
def hbi_cleanup_identity_auth_system_module(
    hbi_maybe_application_identity_auth_system: Application | None,
    hbi_cleanup_module: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by identity auth system which are registered for cleanup
    at the end of the test module
    """
    if hbi_maybe_application_identity_auth_system is not None:
        hbi_cleanup_module(hbi_maybe_application_identity_auth_system.host_inventory)


@pytest.fixture(scope="class", autouse=True)
def hbi_cleanup_identity_auth_system_class(
    hbi_maybe_application_identity_auth_system: Application | None,
    hbi_cleanup_class: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by identity auth system which are registered for cleanup
    at the end of the test class
    """
    if hbi_maybe_application_identity_auth_system is not None:
        hbi_cleanup_class(hbi_maybe_application_identity_auth_system.host_inventory)


@pytest.fixture(scope="function", autouse=True)
def hbi_cleanup_identity_auth_system_function(
    hbi_maybe_application_identity_auth_system: Application | None,
    hbi_cleanup_function: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by identity auth system which are registered for cleanup
    at the end of the test function
    """
    if hbi_maybe_application_identity_auth_system is not None:
        hbi_cleanup_function(hbi_maybe_application_identity_auth_system.host_inventory)


# IDENTITY AUTH SERVICE ACCOUNT


@pytest.fixture(scope="session", autouse=True)
def hbi_cleanup_identity_auth_service_account_session(
    hbi_maybe_application_identity_auth_service_account: Application | None,
    hbi_cleanup_session: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by identity auth service account which are registered for cleanup
    at the end of the test session
    """
    if hbi_maybe_application_identity_auth_service_account is not None:
        hbi_cleanup_session(hbi_maybe_application_identity_auth_service_account.host_inventory)


@pytest.fixture(scope="package", autouse=True)
def hbi_cleanup_identity_auth_service_account_package(
    hbi_maybe_application_identity_auth_service_account: Application | None,
    hbi_cleanup_package: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by identity auth service account which are registered for cleanup
    at the end of the test package
    """
    if hbi_maybe_application_identity_auth_service_account is not None:
        hbi_cleanup_package(hbi_maybe_application_identity_auth_service_account.host_inventory)


@pytest.fixture(scope="module", autouse=True)
def hbi_cleanup_identity_auth_service_account_module(
    hbi_maybe_application_identity_auth_service_account: Application | None,
    hbi_cleanup_module: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by identity auth service account which are registered for cleanup
    at the end of the test module
    """
    if hbi_maybe_application_identity_auth_service_account is not None:
        hbi_cleanup_module(hbi_maybe_application_identity_auth_service_account.host_inventory)


@pytest.fixture(scope="class", autouse=True)
def hbi_cleanup_identity_auth_service_account_class(
    hbi_maybe_application_identity_auth_service_account: Application | None,
    hbi_cleanup_class: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by identity auth service account which are registered for cleanup
    at the end of the test class
    """
    if hbi_maybe_application_identity_auth_service_account is not None:
        hbi_cleanup_class(hbi_maybe_application_identity_auth_service_account.host_inventory)


@pytest.fixture(scope="function", autouse=True)
def hbi_cleanup_identity_auth_service_account_function(
    hbi_maybe_application_identity_auth_service_account: Application | None,
    hbi_cleanup_function: HBICleanupRegistry,
) -> None:
    """
    Deletes all resources created by identity auth service account which are registered for cleanup
    at the end of the test function
    """
    if hbi_maybe_application_identity_auth_service_account is not None:
        hbi_cleanup_function(hbi_maybe_application_identity_auth_service_account.host_inventory)


# SETUP


@pytest.fixture(scope="session", autouse=True)
def hbi_setup_ephemeral_accounts(
    application: Application,
    host_inventory: ApplicationHostInventory,
    hbi_maybe_secondary_user_data: DynaBox | None,
    hbi_maybe_non_org_admin_user_data: DynaBox | None,
) -> None:
    # Skip accounts setup if we are not in an ephemeral environment
    if not application.user_provider_keycloak:
        logger.info("Keycloak is not available in this environment, skipping accounts setup")
        return

    if hbi_maybe_secondary_user_data is None or hbi_maybe_non_org_admin_user_data is None:
        logger.info("Some accounts are not available in the config, skipping accounts setup")
        return

    # Create accounts
    user_provider = UserProvider(application)
    user_provider.get_user_from_config(hbi_maybe_secondary_user_data)
    user_provider.get_user_from_config(hbi_maybe_non_org_admin_user_data)

    # Setup RBAC on non org admin user - remove all permissions
    # There are 2 RBAC groups assigned to non org admin user after the user is created
    # - Custom default access
    #   - doesn't have any roles
    #   - we can't remove the user from this group, because all the users are assigned to it
    # - default access copy
    #   - has default roles for non org admin users
    #   - we have to remove our user from this group
    non_org_admin_username = get_username(hbi_maybe_non_org_admin_user_data)
    host_inventory.apis.rbac.reset_user_groups(
        non_org_admin_username, group_name=None, delete_groups=False
    )


def create_data_on_secondary_account(
    host_inventory_secondary: ApplicationHostInventory,
    *,
    scope: str = "session",
    timeout: int = 20,
    quiet: bool = True,
) -> None:
    logger.info("Creating data for secondary account")

    # Create enough random hosts with all fields populated
    hosts_data = host_inventory_secondary.datagen.create_n_complete_hosts_data(100)
    hosts = host_inventory_secondary.kafka.create_hosts(
        hosts_data=hosts_data,
        timeout=timeout,
        quiet=quiet,
        cleanup_scope=scope,
    )

    # Create enough non-virtual hosts
    hosts_data = host_inventory_secondary.datagen.create_n_complete_hosts_data(
        20, is_virtual=False
    )
    new_hosts = host_inventory_secondary.kafka.create_hosts(
        hosts_data=hosts_data, timeout=timeout, quiet=quiet, cleanup_scope=scope
    )
    hosts += new_hosts

    # Create enough SAP hosts
    hosts_data = host_inventory_secondary.datagen.create_n_complete_hosts_data(
        20, is_sap_system=True
    )
    new_hosts = host_inventory_secondary.kafka.create_hosts(
        hosts_data=hosts_data, timeout=timeout, quiet=quiet, cleanup_scope=scope
    )
    hosts += new_hosts

    # Create enough Edge hosts
    hosts_data = host_inventory_secondary.datagen.create_n_complete_hosts_data(20, is_edge=True)
    new_hosts = host_inventory_secondary.kafka.create_hosts(
        hosts_data=hosts_data, timeout=timeout, quiet=quiet, cleanup_scope=scope
    )
    hosts += new_hosts

    # Create enough image-mode hosts
    hosts_data = host_inventory_secondary.datagen.create_n_complete_hosts_data(
        20, is_image_mode=True
    )
    new_hosts = host_inventory_secondary.kafka.create_hosts(
        hosts_data=hosts_data, timeout=timeout, quiet=quiet, cleanup_scope=scope
    )
    hosts += new_hosts

    # Create enough hosts with some missing values
    hosts_data = host_inventory_secondary.datagen.create_n_hosts_data(20)
    new_hosts = host_inventory_secondary.kafka.create_hosts(
        hosts_data=hosts_data, timeout=timeout, quiet=quiet, cleanup_scope=scope
    )
    hosts += new_hosts

    # Create enough minimal hosts
    hosts_data = host_inventory_secondary.datagen.create_n_minimal_hosts_data(10)
    new_hosts = host_inventory_secondary.kafka.create_hosts(
        hosts_data=hosts_data, timeout=timeout, quiet=quiet, cleanup_scope=scope
    )

    hosts_data = [
        host_inventory_secondary.datagen.create_minimal_host_data(
            subscription_manager_id=generate_uuid()
        )
        for _ in range(10)
    ]
    new_hosts += host_inventory_secondary.kafka.create_hosts(
        hosts_data=hosts_data,
        field_to_match=HostWrapper.subscription_manager_id,
        timeout=timeout,
        quiet=quiet,
        cleanup_scope=scope,
    )
    hosts += new_hosts

    # Create enough groups
    groups = host_inventory_secondary.apis.groups.create_n_empty_groups(50, cleanup_scope=scope)

    # Add enough hosts to groups
    ungrouped_hosts = deepcopy(hosts)
    for i in range(25):
        hosts_to_group = sample(ungrouped_hosts, 5)
        host_inventory_secondary.apis.groups.add_hosts_to_group(groups[i], hosts_to_group)
        for host in hosts_to_group:
            ungrouped_hosts.remove(host)


@pytest.fixture(scope="session", autouse=True)
def hbi_create_data_on_secondary_account(
    hbi_setup_ephemeral_accounts: None,
    request: FixtureRequest,
    application: Application,
    hbi_maybe_application_secondary: Application | None,
) -> None:
    """
    This fixture creates hosts and groups on the secondary account in ephemeral environment.
    This is necessary for testing that one org doesn't have access to another org's data.
    """
    # Don't create data if we are not in an ephemeral environment or sec. account is not configured
    if not application.user_provider_keycloak or hbi_maybe_application_secondary is None:
        return

    # Don't create data if `--skip-data-setup` CLI option was used
    if request.config.getoption("--skip-data-setup"):
        return

    create_data_on_secondary_account(hbi_maybe_application_secondary.host_inventory)


@pytest.fixture(scope="module")
def hbi_recreate_data_on_secondary_account_after_delete(
    application: Application,
    hbi_maybe_application_secondary: Application | None,
) -> Generator[None, None, None]:
    """
    This fixture should be used in all the tests where we delete all hosts or groups
    from the secondary account. This includes all usages of `hosts.confirm_delete_all`,
    `hosts.delete_all`, `hosts.delete_filtered` and `groups.delete_all_groups`.
    This fixture will recreate the necessary data after these tests are finished.
    """
    # Don't create data if we are not in an ephemeral environment or sec. account is not configured
    if not application.user_provider_keycloak or hbi_maybe_application_secondary is None:
        yield
        return

    yield

    create_data_on_secondary_account(hbi_maybe_application_secondary.host_inventory)


@pytest.fixture(scope="session", autouse=True)
def hbi_log_api_request_statistics(host_inventory: ApplicationHostInventory) -> Generator[None]:
    yield
    host_inventory.apis.log_request_statistics()


@pytest.fixture(scope="session", autouse=True)
def setup_ui_hosts_for_catchpoint(
    application: Application,
    hbi_maybe_application_frontend: Application | None,
) -> None:
    """Catchpoint tests (outage tests for Frontend integrated with Status page)
    run via Catchpoint monitoring tool:
    - if account without required hosts - this fixture uploads them with
    'register_for_cleanup=False' param to keep them in the account
    - if account has required hosts - it updates them to keep their staleness "fresh"
    to avoid deletion.

    https://issues.redhat.com/browse/RHINENG-16391
    """
    if application.config.current_env != "prod":
        logger.info(
            "Hosts for Catchpoint required only for prod environment, "
            "skipping hosts update/upload."
        )
        return

    if hbi_maybe_application_frontend is None:
        pytest.fail("frontend user is not properly defined in the config")
    else:
        host_inventory_frontend = hbi_maybe_application_frontend.host_inventory

    catchpoint_rhel_archive = "rhel-82-vuln-patch-advisor.tar.gz"
    unique_id = "_catchpoint"
    hosts = host_inventory_frontend.apis.hosts.get_hosts(display_name=unique_id)
    if len(hosts) != 0:
        hosts_data = [
            HostData(
                display_name=host.display_name,
                subscription_manager_id=host.subscription_manager_id,
                tags=[],
                base_archive=catchpoint_rhel_archive,
            )
            for host in hosts
        ]
    else:
        # if no Catchpoint hosts in the account - create new host_data to upload
        hosts_data = [
            HostData(
                display_name=generate_uuid() + unique_id,
                tags=[],
                base_archive=catchpoint_rhel_archive,
            )
            for _ in range(3)
        ]

    host_inventory_frontend.upload.create_hosts(hosts_data=hosts_data, register_for_cleanup=False)

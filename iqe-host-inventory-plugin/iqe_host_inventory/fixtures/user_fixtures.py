# mypy: disallow-untyped-defs

import logging
from collections.abc import Generator

import pytest
from dynaconf.utils.boxing import DynaBox
from iqe.base.application import Application
from iqe.base.auth import AuthType

from iqe_host_inventory.utils import get_username

logger = logging.getLogger(__name__)


def _get_identity_field(user_data: DynaBox, user_name: str, field: str) -> str:
    if not user_data.get("identity"):
        pytest.fail(f"User {user_name} lacks identity credentials")
    if not user_data.identity.get(field):
        pytest.fail(f"User {user_name} lacks {field}")
    return user_data.identity.get(field)


def get_user(application: Application, name: str) -> DynaBox | None:
    custom_users = application.host_inventory.config.get("users", {})
    iqe_users = application.config.users
    return custom_users.get(name) or iqe_users.get(name)


def require_user(application: Application, name: str) -> DynaBox:
    user = get_user(application, name)
    if user is None:
        pytest.fail(f"User {name} not found in host_inventory config nor IQE config")
    return user


@pytest.fixture(scope="session")
def hbi_default_user(application: Application) -> str:
    custom_default_user = application.host_inventory.config.get("default_user")
    iqe_default_user = application.config.main.default_user
    return custom_default_user or iqe_default_user


@pytest.fixture(scope="session")
def hbi_default_user_data(application: Application, hbi_default_user: str) -> DynaBox:
    return require_user(application, hbi_default_user)


@pytest.fixture(scope="session")
def hbi_default_org_id(hbi_default_user_data: DynaBox, hbi_default_user: str) -> str:
    return _get_identity_field(hbi_default_user_data, hbi_default_user, "org_id")


@pytest.fixture(scope="session")
def hbi_default_account_number(hbi_default_user_data: DynaBox, hbi_default_user: str) -> str:
    return _get_identity_field(hbi_default_user_data, hbi_default_user, "account_number")


@pytest.fixture(scope="session")
def hbi_non_org_admin_user(application: Application) -> str | None:
    return application.host_inventory.config.get("non_org_admin_user")


@pytest.fixture(scope="session")
def hbi_maybe_non_org_admin_user_data(
    application: Application, hbi_non_org_admin_user: str | None
) -> DynaBox | None:
    if hbi_non_org_admin_user is None:
        return None
    return get_user(application, hbi_non_org_admin_user)


@pytest.fixture(scope="session")
def hbi_non_org_admin_user_data(
    application: Application, hbi_non_org_admin_user: str | None
) -> DynaBox:
    assert hbi_non_org_admin_user is not None, (
        "User 'non_org_admin_user' doesn't have a defined name in the config"
    )
    return require_user(application, hbi_non_org_admin_user)


@pytest.fixture(scope="session")
def hbi_non_org_admin_user_username(hbi_non_org_admin_user_data: DynaBox) -> str:
    return get_username(hbi_non_org_admin_user_data)


@pytest.fixture(scope="session")
def hbi_non_org_admin_user_org_id(
    hbi_non_org_admin_user_data: DynaBox, hbi_non_org_admin_user: str
) -> str:
    return _get_identity_field(hbi_non_org_admin_user_data, hbi_non_org_admin_user, "org_id")


@pytest.fixture(scope="session")
def hbi_secondary_user(application: Application) -> str | None:
    return application.host_inventory.config.get("secondary_user")


@pytest.fixture(scope="session")
def hbi_maybe_secondary_user_data(
    application: Application, hbi_secondary_user: str | None
) -> DynaBox | None:
    if hbi_secondary_user is None:
        return None
    return get_user(application, hbi_secondary_user)


@pytest.fixture(scope="session")
def hbi_secondary_user_data(application: Application, hbi_secondary_user: str | None) -> DynaBox:
    assert hbi_secondary_user is not None, (
        "User 'secondary_user' doesn't have a defined name in the config"
    )
    return require_user(application, hbi_secondary_user)


@pytest.fixture(scope="session")
def hbi_secondary_org_id(hbi_secondary_user_data: DynaBox, hbi_secondary_user: str) -> str:
    return _get_identity_field(hbi_secondary_user_data, hbi_secondary_user, "org_id")


@pytest.fixture(scope="session")
def hbi_frontend_user(application: Application) -> str | None:
    return application.host_inventory.config.get("frontend_user")


@pytest.fixture(scope="session")
def hbi_maybe_frontend_user_data(
    application: Application, hbi_frontend_user: str | None
) -> DynaBox | None:
    if hbi_frontend_user is None:
        return None
    return get_user(application, hbi_frontend_user)


@pytest.fixture(scope="session")
def hbi_frontend_user_data(application: Application, hbi_frontend_user: str | None) -> DynaBox:
    assert hbi_frontend_user is not None, (
        "User 'frontend_user' doesn't have a defined name in the config"
    )
    return require_user(application, hbi_frontend_user)


@pytest.fixture(scope="session")
def hbi_frontend_org_id(hbi_frontend_user_data: DynaBox, hbi_frontend_user: str) -> str:
    return _get_identity_field(hbi_frontend_user_data, hbi_frontend_user, "org_id")


@pytest.fixture(scope="session")
def hbi_maybe_service_account_1_data(application: Application) -> DynaBox | None:
    return get_user(application, "inventory_service_account")


@pytest.fixture(scope="session")
def hbi_maybe_service_account_2_data(application: Application) -> DynaBox | None:
    return get_user(application, "inventory_service_account_2")


@pytest.fixture(scope="session")
def hbi_application_cert_auth(
    application: Application, hbi_default_user_data: DynaBox
) -> Generator[Application, None, None]:
    env_for_dynaconf = application.config.current_env.lower()
    with application.copy_using(
        auth_type=AuthType.CERT_AUTH, user=hbi_default_user_data
    ) as new_app:
        if any(env in env_for_dynaconf for env in ("stage", "prod")):
            new_app.config.MAIN.hostname = "cert." + new_app.config.MAIN.hostname
        yield new_app


@pytest.fixture(scope="session")
def hbi_maybe_application_non_org_admin(
    application: Application, hbi_maybe_non_org_admin_user_data: DynaBox | None
) -> Generator[Application | None, None, None]:
    if hbi_maybe_non_org_admin_user_data is None:
        yield None
        return

    with application.copy_using(user=hbi_maybe_non_org_admin_user_data, verify_ssl=False) as app:
        yield app


@pytest.fixture(scope="session")
def hbi_maybe_application_non_org_admin_cert_auth(
    application: Application, hbi_maybe_non_org_admin_user_data: DynaBox | None
) -> Generator[Application | None, None, None]:
    if hbi_maybe_non_org_admin_user_data is None:
        yield None
        return

    env_for_dynaconf = application.config.current_env.lower()
    with application.copy_using(
        auth_type=AuthType.CERT_AUTH, user=hbi_maybe_non_org_admin_user_data
    ) as new_app:
        if any(env in env_for_dynaconf for env in ("stage", "prod")):
            new_app.config.MAIN.hostname = "cert." + new_app.config.MAIN.hostname
        yield new_app


@pytest.fixture(scope="session")
def hbi_maybe_application_secondary(
    application: Application, hbi_maybe_secondary_user_data: DynaBox | None
) -> Generator[Application | None, None, None]:
    if hbi_maybe_secondary_user_data is None:
        yield None
        return

    with application.copy_using(user=hbi_maybe_secondary_user_data, verify_ssl=False) as app:
        yield app


@pytest.fixture(scope="session")
def hbi_application_secondary(hbi_maybe_application_secondary: Application | None) -> Application:
    if hbi_maybe_application_secondary is None:
        pytest.fail("secondary user is not properly defined in the config")
    return hbi_maybe_application_secondary


@pytest.fixture(scope="session")
def hbi_maybe_application_frontend(
    application: Application, hbi_maybe_frontend_user_data: DynaBox | None
) -> Generator[Application | None, None, None]:
    if hbi_maybe_frontend_user_data is None:
        yield None
        return

    with application.copy_using(user=hbi_maybe_frontend_user_data, verify_ssl=False) as app:
        yield app


@pytest.fixture(scope="session")
def hbi_application_frontend(hbi_maybe_application_frontend: Application | None) -> Application:
    if hbi_maybe_application_frontend is None:
        pytest.fail("frontend user is not properly defined in the config")
    return hbi_maybe_application_frontend


@pytest.fixture(scope="session")
def hbi_maybe_application_service_account_1(
    application: Application, hbi_maybe_service_account_1_data: DynaBox | None
) -> Generator[Application | None, None, None]:
    if hbi_maybe_service_account_1_data is None:
        yield None
        return

    with application.copy_using(
        user=hbi_maybe_service_account_1_data, auth_type=AuthType.JWT_AUTH, verify_ssl=False
    ) as app:
        yield app


@pytest.fixture(scope="session")
def hbi_maybe_application_service_account_2(
    application: Application, hbi_maybe_service_account_2_data: DynaBox | None
) -> Generator[Application | None, None, None]:
    if hbi_maybe_service_account_2_data is None:
        yield None
        return

    with application.copy_using(
        user=hbi_maybe_service_account_2_data, auth_type=AuthType.JWT_AUTH, verify_ssl=False
    ) as app:
        yield app

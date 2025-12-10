import logging
import time
from collections.abc import Generator

import pytest
from iqe.base.application import Application
from iqe.base.feature_flags import get_feature_flag_backend
from iqe.base.feature_flags.consoledot_proxy import ConsoleDotProxyBackend
from iqe.base.feature_flags.unleash import UnleashBackend
from iqe.base.feature_flags.unleash import UnleashFlagRequest
from iqe.base.feature_flags.unleash import _RequestType

from iqe_host_inventory import ApplicationHostInventory

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def unleash(application: Application) -> UnleashBackend | ConsoleDotProxyBackend:
    if application.config.current_env in ["ephemeral", "clowder_smoke"]:
        unleash = get_feature_flag_backend("unleash", application)
    else:
        unleash = application.feature_flag

    return unleash


def toggle_feature_flag(
    unleash: UnleashBackend | ConsoleDotProxyBackend, flag: str, enable: bool = True
):
    """Help function to toggle feature flag.

    Toggling a feature flag is possible only in ephemeral environments.
    In the stage/prod environment, this function checks the value of the flag.
    If it is different from the `enable` parameter, it skips the test.

    """
    if isinstance(unleash, UnleashBackend):
        logger.info(f"Switching '{flag}' feature flag to: {enable}")
        if enable:
            unleash.admin.enable_flag(flag)
        else:
            unleash.admin.disable_flag(flag)
        time.sleep(2)  # HBI Unleash cache gets refreshed every second in ephemeral
    elif isinstance(unleash, ConsoleDotProxyBackend):
        if enable == unleash.is_enabled(flag):
            logger.info(f"'{flag}' feature flag already set to: {enable}.")
        else:
            pytest.xfail(
                f"'{flag}' feature flag is set to {unleash.is_enabled(flag)} "
                f"in current environment."
            )


# Kessel workspace migration


def _ensure_ungrouped_group_exists(host_inventory: ApplicationHostInventory):
    # This is a workaround to ensure the group exists in a new environment as tests may expect it.
    if not host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts"):
        # If the ungrouped group doesn't exist, it will get created with this
        host = host_inventory.upload.create_host()

        assert host_inventory.apis.groups.get_groups(group_type="ungrouped-hosts"), (
            "The ungrouped group doesn't exist"
        )

        host_inventory.apis.hosts.delete_by_id(host)


# Kessel UI


@pytest.fixture(scope="session")
def kessel_workspace_ui_flag(unleash: UnleashBackend | ConsoleDotProxyBackend) -> str:
    feature_flag = "hbi.kessel-migration"

    if isinstance(unleash, UnleashBackend) and not unleash.has_flag(feature_flag):
        flag_request = UnleashFlagRequest(
            name=feature_flag,
            description="UI kessel_workspace_migration flag",
            type=_RequestType.RELEASE,
            impressionData=False,
        )
        unleash.admin.create_flag(flag_request=flag_request)

    return feature_flag


@pytest.fixture(scope="session")
def enabled_ui_kessel(
    unleash: UnleashBackend | ConsoleDotProxyBackend,
    kessel_workspace_ui_flag: str,
    host_inventory_frontend: ApplicationHostInventory,
) -> bool:
    # condition to not skip test that required disabled kessel flag
    # in stage/prod environment
    if isinstance(unleash, UnleashBackend):
        toggle_feature_flag(unleash, kessel_workspace_ui_flag)

        _ensure_ungrouped_group_exists(host_inventory_frontend)

    return unleash.is_enabled(kessel_workspace_ui_flag)


# Kessel Phase 1


@pytest.fixture(scope="session")
def kessel_phase_1_flag(unleash: UnleashBackend | ConsoleDotProxyBackend) -> str:
    feature_flag = "hbi.api.kessel-phase-1"

    if isinstance(unleash, UnleashBackend) and not unleash.has_flag(feature_flag):
        flag_request = UnleashFlagRequest(
            name=feature_flag,
            description="kessel_phase_1 flag",
            type=_RequestType.RELEASE,
            impressionData=False,
        )
        unleash.admin.create_flag(flag_request=flag_request)

    return feature_flag


@pytest.fixture
def enable_kessel_phase_1(
    unleash: UnleashBackend | ConsoleDotProxyBackend,
    kessel_phase_1_flag: str,
) -> Generator[None, None, None]:
    toggle_feature_flag(unleash, kessel_phase_1_flag)

    yield

    toggle_feature_flag(unleash, kessel_phase_1_flag, enable=False)


@pytest.fixture(scope="module")
def enable_kessel_phase_1_module(
    unleash: UnleashBackend | ConsoleDotProxyBackend,
    kessel_phase_1_flag: str,
) -> Generator[None, None, None]:
    toggle_feature_flag(unleash, kessel_phase_1_flag)

    yield

    toggle_feature_flag(unleash, kessel_phase_1_flag, enable=False)


@pytest.fixture(scope="session")
def enable_kessel_phase_1_session(
    unleash: UnleashBackend | ConsoleDotProxyBackend,
    kessel_phase_1_flag: str,
) -> Generator[None, None, None]:
    toggle_feature_flag(unleash, kessel_phase_1_flag)

    yield

    toggle_feature_flag(unleash, kessel_phase_1_flag, enable=False)


@pytest.fixture()
def is_kessel_phase_1_enabled(unleash: UnleashBackend | ConsoleDotProxyBackend):
    return unleash.is_enabled("hbi.api.kessel-phase-1")


# Workloads fields backward compatibility


@pytest.fixture(scope="session")
def enable_workloads_fields_backward_compatibility_session(
    unleash: UnleashBackend | ConsoleDotProxyBackend,
    workloads_fields_backward_compatibility_flag: str,
) -> Generator[None, None, None]:
    toggle_feature_flag(unleash, workloads_fields_backward_compatibility_flag)

    yield

    toggle_feature_flag(unleash, workloads_fields_backward_compatibility_flag, enable=False)


@pytest.fixture(scope="session")
def workloads_fields_backward_compatibility_flag(
    unleash: UnleashBackend | ConsoleDotProxyBackend,
) -> str:
    feature_flag = "hbi.workloads_fields_backward_compatibility"

    if isinstance(unleash, UnleashBackend) and not unleash.has_flag(feature_flag):
        flag_request = UnleashFlagRequest(
            name=feature_flag,
            description="hbi.workloads_fields_backward_compatibility flag",
            type=_RequestType.RELEASE,
            impressionData=False,
        )
        unleash.admin.create_flag(flag_request=flag_request)

    return feature_flag

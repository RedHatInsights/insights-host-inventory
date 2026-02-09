import logging
from collections.abc import Generator

import pytest
from iqe.base.feature_flags.unleash import UnleashBackend

from iqe_host_inventory import ApplicationHostInventory

logger = logging.getLogger(__name__)


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
def kessel_workspace_ui_flag(host_inventory_frontend: ApplicationHostInventory) -> str:
    return host_inventory_frontend.unleash.kessel_workspace_ui_flag


@pytest.fixture(scope="session")
def enabled_ui_kessel(
    kessel_workspace_ui_flag: str, host_inventory_frontend: ApplicationHostInventory
) -> bool:
    # condition to not skip test that required disabled kessel flag
    # in stage/prod environment
    if isinstance(host_inventory_frontend.unleash._unleash, UnleashBackend):
        host_inventory_frontend.unleash.toggle_feature_flag(kessel_workspace_ui_flag)

        _ensure_ungrouped_group_exists(host_inventory_frontend)

    return host_inventory_frontend.unleash.is_flag_enabled(kessel_workspace_ui_flag)


# Kessel Phase 1


@pytest.fixture
def enable_kessel_phase_1(host_inventory: ApplicationHostInventory) -> Generator[None, None, None]:
    host_inventory.unleash.toggle_feature_flag(
        host_inventory.unleash.kessel_phase_1_flag, enable=True
    )

    yield

    host_inventory.unleash.toggle_feature_flag(
        host_inventory.unleash.kessel_phase_1_flag, enable=False
    )


@pytest.fixture(scope="module")
def enable_kessel_phase_1_module(
    host_inventory: ApplicationHostInventory,
) -> Generator[None, None, None]:
    host_inventory.unleash.toggle_feature_flag(
        host_inventory.unleash.kessel_phase_1_flag, enable=True
    )

    yield

    host_inventory.unleash.toggle_feature_flag(
        host_inventory.unleash.kessel_phase_1_flag, enable=False
    )


@pytest.fixture(scope="session")
def enable_kessel_phase_1_session(
    host_inventory: ApplicationHostInventory,
) -> Generator[None, None, None]:
    host_inventory.unleash.toggle_feature_flag(
        host_inventory.unleash.kessel_phase_1_flag, enable=True
    )

    yield

    host_inventory.unleash.toggle_feature_flag(
        host_inventory.unleash.kessel_phase_1_flag, enable=False
    )


@pytest.fixture(scope="session")
def is_kessel_phase_1_enabled_session(host_inventory: ApplicationHostInventory):
    return host_inventory.unleash.is_kessel_phase_1_enabled()

import logging
from collections.abc import Generator

import pytest

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


# Kessel Groups (RBAC v2 workspace support)
# Note: Flag definition moved to HBIUnleash.kessel_groups_flag property
# in iqe_host_inventory/modeling/unleash.py


@pytest.fixture
def enable_kessel_groups(
    host_inventory: ApplicationHostInventory,
) -> Generator[None, None, None]:
    host_inventory.unleash.toggle_feature_flag(
        host_inventory.unleash.kessel_groups_flag, enable=True
    )

    yield

    host_inventory.unleash.toggle_feature_flag(
        host_inventory.unleash.kessel_groups_flag, enable=False
    )


@pytest.fixture(scope="module")
def enable_kessel_groups_module(
    host_inventory: ApplicationHostInventory,
) -> Generator[None, None, None]:
    host_inventory.unleash.toggle_feature_flag(
        host_inventory.unleash.kessel_groups_flag, enable=True
    )

    yield

    host_inventory.unleash.toggle_feature_flag(
        host_inventory.unleash.kessel_groups_flag, enable=False
    )


@pytest.fixture(scope="session")
def enable_kessel_groups_session(
    host_inventory: ApplicationHostInventory,
) -> Generator[None, None, None]:
    host_inventory.unleash.toggle_feature_flag(
        host_inventory.unleash.kessel_groups_flag, enable=True
    )

    yield

    host_inventory.unleash.toggle_feature_flag(
        host_inventory.unleash.kessel_groups_flag, enable=False
    )


@pytest.fixture(scope="session")
def is_kessel_groups_enabled_session(host_inventory: ApplicationHostInventory):
    return host_inventory.unleash.is_kessel_groups_enabled()

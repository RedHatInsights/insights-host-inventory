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
def enable_rbac_workspaces(
    host_inventory: ApplicationHostInventory,
) -> Generator[None, None, None]:
    host_inventory.unleash.toggle_feature_flag(
        host_inventory.unleash.rbac_workspaces_flag, enable=True
    )

    yield

    host_inventory.unleash.toggle_feature_flag(
        host_inventory.unleash.rbac_workspaces_flag, enable=False
    )


@pytest.fixture(scope="module")
def enable_rbac_workspaces_module(
    host_inventory: ApplicationHostInventory,
) -> Generator[None, None, None]:
    host_inventory.unleash.toggle_feature_flag(
        host_inventory.unleash.rbac_workspaces_flag, enable=True
    )

    yield

    host_inventory.unleash.toggle_feature_flag(
        host_inventory.unleash.rbac_workspaces_flag, enable=False
    )


@pytest.fixture(scope="session")
def enable_rbac_workspaces_session(
    host_inventory: ApplicationHostInventory,
) -> Generator[None, None, None]:
    host_inventory.unleash.toggle_feature_flag(
        host_inventory.unleash.rbac_workspaces_flag, enable=True
    )

    yield

    host_inventory.unleash.toggle_feature_flag(
        host_inventory.unleash.rbac_workspaces_flag, enable=False
    )


@pytest.fixture(scope="session")
def is_rbac_workspaces_enabled_session(host_inventory: ApplicationHostInventory):
    return host_inventory.unleash.is_rbac_workspaces_enabled
